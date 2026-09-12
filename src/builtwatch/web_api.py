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
    from .quality import dependency_mismatch, friendly_failure, unverified

    findings = []
    quality = []
    systems = store.list_systems()
    ids = {s.id for s in systems}
    for finding in store.list_findings(limit=300):
        if finding.system_id not in ids:
            continue
        profile = next(s for s in systems if s.id == finding.system_id)
        if unverified(finding):
            quality.append(
                {
                    "system_id": finding.system_id,
                    "source_id": finding.source_id,
                    "message": (
                        "An assessment could not be verified and was withheld. "
                        "No action is requested."
                    ),
                }
            )
            continue
        if finding.source_id == "cisa-kev" and dependency_mismatch(
            profile, " ".join([finding.title, *finding.facts, *finding.inferences])
        ):
            continue
        item = finding.model_dump(mode="json")
        actions = store.dispositions_for(finding.id)
        decisions = [a for a in actions if a.action.value != "exported"]
        item["disposition"] = decisions[-1].action.value if decisions else "open"
        findings.append(item)
    runs = [r.model_dump(mode="json") for r in store.list_runs()]
    for run in runs:
        run["abort_reason"] = friendly_failure(run["abort_reason"])
        # Internal cost estimates are for owner operations only, not workspace users.
        run.pop("estimated_cost_usd", None)
        for health in run["source_health"]:
            if health.get("error"):
                health["error"] = "This source could not be retrieved. Coverage is incomplete."
    agent_reviews = []
    if hasattr(store, "get"):
        agent_reviews = [
            review
            for system in systems
            if (review := store.get("agent-review#" + system.id))
        ]
    return {
        "quality": quality,
        "systems": [s.model_dump(mode="json") for s in systems],
        "findings": findings,
        "agent_reviews": agent_reviews,
        "sources": [s.model_dump(mode="json") for s in load_registry(settings.registry_path)],
        "runs": runs,
        "demo": False,
    }


def authorized(event: dict) -> bool:
    token = os.environ.get("BW_OWNER_TOKEN", "")
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    return bool(token) and hmac.compare_digest(headers.get("authorization", ""), f"Bearer {token}")


def response(status: int, body: Any, cache_control: str = "no-store") -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": cache_control,
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
        if path == "/api/systems/bulk" and method == "POST":
            items = body.get("systems")
            if not isinstance(items, list) or not 1 <= len(items) <= MAX_WEB_SYSTEMS:
                raise ValueError("Import between one and ten app profiles")
            profiles = [SystemPassport.model_validate(x) for x in items]
            ids = [x.id for x in profiles]
            if len(set(ids)) != len(ids):
                raise ValueError("Each imported app needs a different ID")
            if any(not x.name.strip() or not x.purpose.strip() for x in profiles):
                raise ValueError("Each app needs a name and purpose")
            existing = {x.id for x in store.list_systems()}
            if len(existing | set(ids)) > MAX_WEB_SYSTEMS:
                return response(409, {"error": "Your workspace supports ten apps in total"})
            # Validate the entire batch before any writes; stable IDs make network retries safe.
            for profile in profiles:
                store.upsert_system(profile)
            return response(200, {"imported": len(profiles), "updated": len(existing & set(ids))})
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
            if hasattr(store, "get") and hasattr(store, "delete"):
                finding = store.get_finding(body["finding_id"])
                pending = store.get("agent-review#" + finding.system_id)
                if pending and pending.get("finding_id") == body["finding_id"]:
                    store.delete("agent-review#" + pending["system_id"])
            return response(200, {"saved": True})
        if path == "/api/scan" and method == "POST":
            if not store.list_systems():
                return response(409, {"error": "Add a system before checking sources."})
            if store.spent_this_month() >= settings.limits.max_cost_per_month_usd:
                return response(
                    429, {"error": "The workspace check limit has been reached. Try again later."}
                )
            if store.spent_today() >= settings.limits.max_cost_per_day_usd:
                return response(
                    429, {"error": "Today's check limit has been reached. Try again tomorrow."}
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
