"""Verified account boundary and bounded background scan coordination."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from decimal import Decimal
from http import HTTPStatus
from typing import Any

from botocore.exceptions import ClientError

from .dynamo_store import DynamoStore
from .web_api import dispatch, response

SIGNATURE_AGE = 300
COST_STATUS_MAX_AGE = 172800
RESERVATION = Decimal("1.00")
GLOBAL_MONTH_LIMIT = Decimal("5.00")


def verify(event: dict, secret: str, table: Any) -> str | None:
    """Authenticate before selecting a partition; consume signed nonces once."""
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    tenant = headers.get("x-bw-account", "")
    stamp = headers.get("x-bw-time", "")
    nonce = headers.get("x-bw-nonce", "")
    signature = headers.get("x-bw-signature", "")
    if not secret or not re.fullmatch(r"[a-f0-9]{64}", tenant):
        return None
    if not re.fullmatch(r"[a-f0-9-]{36}", nonce) or not stamp.isdigit():
        return None
    if abs(time.time() - int(stamp)) > SIGNATURE_AGE:
        return None
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw, validate=True).decode()
        except (ValueError, UnicodeDecodeError):
            return None
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    message = "\n".join(
        [
            method,
            event.get("rawPath", ""),
            tenant,
            stamp,
            nonce,
            hashlib.sha256(raw.encode()).hexdigest(),
        ]
    )
    expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        table.put_item(
            Item={
                "pk": "NONCE#" + tenant,
                "sk": nonce,
                "expires": int(time.time()) + SIGNATURE_AGE * 2,
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return None
        raise
    return tenant


def reserve_budget(table: Any, month: str) -> bool:
    control = table.get_item(Key={"pk": "ADMIN", "sk": "snapshot"}).get("Item", {})
    manual = table.get_item(Key={"pk": "ADMIN", "sk": "control"}).get("Item", {})
    if (
        manual.get("paused")
        or (os.environ.get("BW_COST_GUARD_REQUIRED") == "true" and not control.get("checked_at"))
        or control.get("paused")
        or (
            control.get("checked_at")
            and time.time() - float(control["checked_at"]) > COST_STATUS_MAX_AGE
        )
    ):
        return False
    try:
        table.update_item(
            Key={"pk": "BUDGET", "sk": month},
            UpdateExpression="ADD allocated :amount",
            ConditionExpression="attribute_not_exists(allocated) OR allocated <= :remaining",
            ExpressionAttributeValues={
                ":amount": RESERVATION,
                ":remaining": GLOBAL_MONTH_LIMIT - RESERVATION,
            },
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def settle_budget(table: Any, month: str, cost: float) -> None:
    # A timed-out worker cannot settle: its full reservation remains charged conservatively.
    table.update_item(
        Key={"pk": "BUDGET", "sk": month},
        UpdateExpression="ADD allocated :refund",
        ExpressionAttributeValues={":refund": Decimal(str(cost)) - RESERVATION},
    )


def serve(event: dict, store: DynamoStore, settings: Any, invoke: Any) -> dict:
    method = event["requestContext"]["http"]["method"]
    path = event.get("rawPath", "")
    if method == "GET":
        result = dispatch(event, store, settings, lambda: None, verified=True)
        if path == "/api/workspace" and result["statusCode"] == HTTPStatus.OK:
            data = json.loads(result["body"])
            data["job"] = store.job()
            if data["job"].get("status") == "failed":
                data["job"]["message"] = (
                    "The check could not finish reliably. Completed results are saved."
                )
            elif data["job"].get("status") == "aborted":
                data["job"]["message"] = (
                    "The check stopped early. See check history; the demo remains available."
                )
            data["draft"] = store.get("intake-draft")
            data["account"] = {
                "automatic_checks": (store.get("preferences") or {}).get("automatic_checks", True),
                "viewer_lens": (store.get("preferences") or {}).get("viewer_lens", "business"),
            }
            result = response(200, data)
        return result
    lock = str(uuid.uuid4())
    if not store.acquire_lock(lock):
        return response(
            409,
            {
                "error": (
                    "A check is in progress. You can read your workspace; "
                    "changes will be available when it finishes."
                )
            },
        )
    try:
        body = {}
        if path in {"/api/intake", "/api/preferences", "/api/agent/sync"} and method == "POST":
            try:
                raw = event.get("body") or "{}"
                if event.get("isBase64Encoded"):
                    raw = base64.b64decode(raw, validate=True).decode()
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise ValueError("Expected an object")
            except (ValueError, TypeError, UnicodeDecodeError):
                return response(400, {"error": "Please send a valid JSON object."})
        if path == "/api/agent/sync" and method == "POST":
            from .models import SystemPassport
            from .web_api import MAX_WEB_SYSTEMS, workspace

            system_id = body.get("system_id", "")
            if not re.fullmatch(r"agent-[a-f0-9-]{12}", system_id):
                return response(400, {"error": "Invalid connection system"})
            if "profile" in body:
                try:
                    profile = SystemPassport.model_validate(body["profile"])
                    if (
                        profile.id != system_id
                        or not profile.name.strip()
                        or not profile.purpose.strip()
                    ):
                        raise ValueError("Profile must match the connected system")
                    existing = store.get_system(system_id)
                    if not existing and len(store.list_systems()) >= MAX_WEB_SYSTEMS:
                        return response(409, {"error": "Your workspace supports ten systems"})
                    if existing:
                        profile.created_at = existing.created_at
                    if not profile.source_agent:
                        profile.source_agent = "Connected project agent"
                    store.upsert_system(profile)
                except (ValueError, TypeError):
                    return response(400, {"error": "Send a valid system profile"})
            result = workspace(store, settings)
            return response(
                200,
                {
                    "system": next((x for x in result["systems"] if x["id"] == system_id), None),
                    "findings": [x for x in result["findings"] if x["system_id"] == system_id],
                    "sources": result["sources"],
                    "latest_check": (
                        {k: result["runs"][0][k] for k in ("started_at", "status", "source_health")}
                        if result["runs"]
                        else None
                    ),
                    "next_sync": "After midnight UTC tomorrow",
                    "instructions": "Verify finding evidence before changes.",
                },
            )
        if path == "/api/intake" and method == "POST":
            from .web_intake import queue_intake

            return queue_intake(store, settings, body, invoke)
        if path == "/api/intake" and method == "DELETE":
            store.delete("intake-draft")
            return response(200, {"deleted": True})
        if path == "/api/preferences" and method == "POST":
            updates = {}
            if "automatic_checks" in body:
                if not isinstance(body["automatic_checks"], bool):
                    return response(400, {"error": "Choose whether automatic checks are enabled."})
                updates["automatic_checks"] = body["automatic_checks"]
            if "viewer_lens" in body:
                if body["viewer_lens"] not in ("business", "operations", "technical"):
                    return response(
                        400, {"error": "Choose Business, Operations or Technical view."}
                    )
                updates["viewer_lens"] = body["viewer_lens"]
            if not updates:
                return response(400, {"error": "No supported preference supplied."})
            store.put("preferences", {**(store.get("preferences") or {}), **updates})
            return response(200, {"saved": True})

        def enqueue() -> None:
            job = {
                "id": str(uuid.uuid4()),
                "status": "queued",
                "requested_at": time.time(),
                "message": "Your check is queued. You can leave this page.",
            }
            store.put("job", job)
            try:
                invoke({"task": "scan", "tenant": store.tenant, "job_id": job["id"]})
            except Exception:
                store.put(
                    "job",
                    {
                        **job,
                        "status": "failed",
                        "message": "The check could not start. Please retry.",
                    },
                )
                store.clear_cooldown()
                raise

        return dispatch(event, store, settings, enqueue, verified=True)
    finally:
        store.release_lock(lock)


def work(event: dict, store: DynamoStore, settings: Any, scan: Any) -> dict:
    job = store.get("job") or {}
    if job.get("id") != event.get("job_id") or job.get("status") != "queued":
        return {"status": "skipped"}
    lock = str(uuid.uuid4())
    if not store.acquire_lock(lock):
        # Lambda retries this event after the API has released its brief write lock.
        raise RuntimeError("Workspace is busy")
    try:
        # A duplicate queued event may have waited on a prior worker.
        job = store.get("job") or {}
        if job.get("id") != event.get("job_id") or job.get("status") != "queued":
            return {"status": "skipped"}
        month = time.strftime("%Y-%m", time.gmtime())
        if not reserve_budget(store.table, month):
            store.put(
                "job",
                {
                    **job,
                    "status": "paused",
                    "message": (
                        "The shared pilot model allowance is used or reserved. "
                        "Try later, or next month."
                    ),
                },
            )
            return {"status": "paused"}
        store.put(
            "job",
            {
                **job,
                "status": "running",
                "started_at": time.time(),
                "message": "Checking sources and assessing relevance. You can leave this page.",
            },
        )
        try:
            result = scan(store, settings, mode="live")
            settle_budget(store.table, month, result.run.estimated_cost_usd)
            store.put(
                "job",
                {
                    **job,
                    "status": result.run.status,
                    "run_id": result.run.id,
                    "message": result.summary_line(),
                },
            )
            return {"status": result.run.status}
        except Exception:
            store.put(
                "job",
                {
                    **job,
                    "status": "failed",
                    "message": (
                        "The check was interrupted. Coverage is incomplete; please try again later."
                    ),
                },
            )
            raise
    finally:
        store.release_lock(lock)
