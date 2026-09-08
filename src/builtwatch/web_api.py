"""Owner workspace API. Anonymous visitors cannot read inventory or invoke models."""

from __future__ import annotations

import base64
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .models import Disposition, DispositionAction, SystemPassport
from .registry import load_registry
from .store import Store, new_id

MAX_PROFILE_BYTES = 24000
MAX_WEB_SYSTEMS = 10
SCAN_COOLDOWN_SECONDS = 1800


def workspace(store: Store, settings: Settings) -> dict[str, Any]:
    findings = []
    systems = store.list_systems()
    ids = {s.id for s in systems}
    for finding in store.list_findings(limit=300):
        if finding.system_id not in ids:
            continue
        item = finding.model_dump(mode="json")
        actions = store.dispositions_for(finding.id)
        decisions = [a for a in actions if a.action.value != "exported"]
        item["disposition"] = decisions[-1].action.value if decisions else "open"
        findings.append(item)
    return {
        "systems": [s.model_dump(mode="json") for s in systems],
        "findings": findings,
        "sources": [s.model_dump(mode="json") for s in load_registry(settings.registry_path)],
        "runs": [r.model_dump(mode="json") for r in store.list_runs()],
        "spend": {
            "month": store.spent_this_month(),
            "day": store.spent_today(),
            "limit": settings.limits.max_cost_per_month_usd,
        },
        "demo": False,
    }


def authorized(event: dict) -> bool:
    token = os.environ.get("BW_OWNER_TOKEN", "")
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    return bool(token) and hmac.compare_digest(headers.get("authorization", ""), f"Bearer {token}")


def response(status: int, body: Any) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
        "body": json.dumps(body),
    }


def dispatch(
    event: dict, store: Store, settings: Settings, enqueue, *, verified: bool = False
) -> dict:
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/")
    if not verified and not authorized(event):
        return response(401, {"error": "Connect with your workspace access key."})
    try:
        raw = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode()
        if len(raw) > MAX_PROFILE_BYTES:
            return response(413, {"error": "Please keep the profile under 24 KB."})
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError("Expected a JSON object")
        if path == "/api/workspace" and method == "GET":
            return response(200, workspace(store, settings))
        if path == "/api/systems" and method == "POST":
            passport = SystemPassport.model_validate(body)
            if not passport.name.strip() or not passport.purpose.strip():
                raise ValueError("Name and purpose are required")
            if not store.get_system(passport.id) and len(store.list_systems()) >= MAX_WEB_SYSTEMS:
                return response(409, {"error": "This workspace supports up to 10 systems."})
            store.upsert_system(passport)
            return response(200, {"system": passport.model_dump(mode="json")})
        if path.startswith("/api/systems/") and method == "DELETE":
            return response(200, {"deleted": store.delete_system(path.split("/")[-1])})
        if path == "/api/dispositions" and method == "POST":
            if not store.get_finding(body.get("finding_id", "")):
                return response(404, {"error": "Finding not found"})
            action = DispositionAction(body.get("action"))
            reason = str(body.get("reason", ""))[:1000]
            if action == DispositionAction.DISMISSED and not reason.strip():
                raise ValueError("Add a reason for dismissing this finding")
            item = Disposition(
                id=new_id("disp"), finding_id=body["finding_id"], action=action, reason=reason
            )
            store.add_disposition(item)
            return response(200, {"saved": True})
        if path == "/api/scan" and method == "POST":
            if not store.list_systems():
                return response(409, {"error": "Add a system before checking sources."})
            if store.spent_this_month() >= settings.limits.max_cost_per_month_usd:
                return response(429, {"error": "Monthly model allowance reached."})
            if store.spent_today() >= settings.limits.max_cost_per_day_usd:
                return response(
                    429, {"error": "Daily model allowance reached. Try again tomorrow."}
                )
            now = datetime.now(timezone.utc).timestamp()
            if not store.reserve_scan(now, SCAN_COOLDOWN_SECONDS):
                return response(
                    429, {"error": "A check was requested recently. Try again in 30 minutes."}
                )
            enqueue()
            return response(202, {"queued": True})
        return response(404, {"error": "Route not found"})
    except (ValueError, TypeError, KeyError) as exc:
        return response(400, {"error": str(exc)[:500]})
