"""Verified account boundary and bounded background scan coordination."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
RESERVATION = Decimal("1.00")
GLOBAL_MONTH_LIMIT = Decimal("10.00")


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
            data["account"] = {
                "automatic_checks": (store.get("preferences") or {}).get("automatic_checks", True)
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
        if path == "/api/preferences" and method == "POST":
            body = json.loads(event.get("body") or "{}")
            enabled = body.get("automatic_checks")
            if not isinstance(enabled, bool):
                return response(400, {"error": "Choose whether automatic checks are enabled."})
            store.put("preferences", {"automatic_checks": enabled})
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
