"""Verified account boundary and bounded background scan coordination."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from http import HTTPStatus
from typing import Any
from zoneinfo import ZoneInfo

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from .dynamo_store import DynamoStore
from .web_api import dispatch, response

SIGNATURE_AGE = 300
COST_STATUS_MAX_AGE = 172800
# Reserve only the per-run model ceiling. This bounds concurrent work without
# reserving a larger amount than a run can spend.
RESERVATION = Decimal("0.25")
# Returned to connected agents whose app has no backend map yet. Agents already syncing
# learn about maps from the response; nothing here is fetched or executed by BuiltWatch.
BACKEND_MAP_REQUEST = (
    "Optional: include profile.architecture so BuiltWatch can show which part of this app "
    "each outside change reaches. Shape: {\"analyzed_by\":\"<agent>\",\"analyzed_at\":"
    "\"YYYY-MM-DD\",\"components\":[{\"id\":\"slug\",\"name\":\"...\",\"kind\":"
    "\"entry|service|data|model|external\",\"purpose\":\"...\",\"uses\":[],\"data\":[],"
    "\"actions\":[]}],\"flows\":[{\"source\":\"id\",\"target\":\"id\",\"label\":\"...\"}]}. "
    "Every uses/data/actions entry must repeat a value already in the profile's services or "
    "technologies, data_categories or consequential_actions; add it there first. At most 24 "
    "components and 48 flows; keep the whole request under 24 KB. Read the code locally and "
    "never include source code, secrets, tokens, internal URLs or customer records."
)


def _first_error(exc: Exception) -> str:
    """The first validation problem (field and rule), so an agent can fix its request."""
    errors = getattr(exc, "errors", None)
    if callable(errors):
        with contextlib.suppress(Exception):
            first = errors()[0]
            where = ".".join(str(x) for x in first.get("loc", ()))
            message = str(first.get("msg", "invalid value"))
            return f"{where}: {message}"[:300] if where else message[:300]
    return str(exc).splitlines()[0][:300]
GLOBAL_MONTH_LIMIT = Decimal("2.00")
PUBLIC_IMPACT_TTL = 900


def public_impact(table: Any) -> dict[str, Any]:
    """Compute anonymous aggregate totals for the public Impact page.

    Only coarse counters leave this function. Tenant identifiers, app names,
    evidence, prompts, and source URLs remain inside the account table. Computing
    them reads every tenant partition, and the inputs change only when a daily check
    finishes or an outcome is recorded, so results are cached for fifteen minutes.
    """
    now = time.time()
    cached = table.get_item(Key={"pk": "GLOBAL", "sk": "impact"}).get("Item") or {}
    try:
        if float(cached.get("expires_at", 0)) > now:
            return json.loads(cached.get("payload", "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    directories: list[dict] = []
    args = {"KeyConditionExpression": Key("pk").eq("DIRECTORY")}
    while True:
        page = table.query(**args)
        directories.extend(page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            break
        args["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    systems = evaluations = reviews = no_action = detail_needed = outcomes = 0
    apps_needing_review: set[tuple[str, str]] = set()
    last_activity = 0.0
    for directory in directories:
        tenant = str(directory.get("sk", ""))
        if not re.fullmatch(r"[a-f0-9]{64}", tenant):
            continue
        pk = "USER#" + tenant
        rows: list[dict] = []
        query = {"KeyConditionExpression": Key("pk").eq(pk), "ProjectionExpression": "sk, payload"}
        while True:
            page = table.query(**query)
            rows.extend(page.get("Items", []))
            if "LastEvaluatedKey" not in page:
                break
            query["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        findings: dict[str, dict] = {}
        latest_actions: dict[str, str] = {}
        legacy_review_events = 0
        has_review_metric = False
        has_detail_metric = False
        legacy_detail_events = 0
        for item in rows:
            key = str(item.get("sk", ""))
            try:
                value = json.loads(item.get("payload", "{}"))
            except (TypeError, json.JSONDecodeError):
                continue
            if key.startswith("system#"):
                systems += 1
            elif key.startswith("run#") and value.get("status") == "complete":
                raw_evaluations = value.get("evaluations_performed")
                if raw_evaluations is None:
                    raw_evaluations = len(value.get("systems_evaluated", []))
                evaluations += int(raw_evaluations)
                raw_reviews = value.get("review_events_created")
                if raw_reviews is not None:
                    has_review_metric = True
                    reviews += int(raw_reviews)
                raw_no_action = value.get("no_action_evaluations")
                if raw_no_action is not None:
                    no_action += int(raw_no_action)
                raw_detail = value.get("detail_needed_evaluations")
                if raw_detail is not None:
                    has_detail_metric = True
                    detail_needed += int(raw_detail)
                stamp = value.get("finished_at")
                if stamp:
                    with contextlib.suppress(TypeError, ValueError):
                        finished = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                        last_activity = max(last_activity, finished.timestamp())
            elif key.startswith("finding#"):
                findings[str(value.get("id", key[8:]))] = value
            elif key.startswith("disposition#"):
                finding_id = str(value.get("finding_id", ""))
                if finding_id and value.get("action") in {"acknowledged", "dismissed"}:
                    outcomes += 1
                    created = str(value.get("created_at", ""))
                    if created > latest_actions.get(finding_id, ""):
                        latest_actions[finding_id] = created
        for finding_id, finding in findings.items():
            if finding.get("relevance") == "relevant":
                if finding_id not in latest_actions:
                    apps_needing_review.add((tenant, str(finding.get("system_id", ""))))
                # Runs written before metric fields existed still contribute a
                # visible lower bound: one currently known match is one event.
                if not has_review_metric:
                    legacy_review_events += 1
            elif finding.get("relevance") == "insufficient_information":
                legacy_detail_events += 1
        reviews += legacy_review_events
        if not has_detail_metric:
            detail_needed += legacy_detail_events

    if last_activity <= 0:
        last_activity = now
    # Older runs may contain findings but not the explicit outcome counters. Keep
    # the public breakdown conservative and internally consistent in that case.
    remaining = max(0, evaluations)
    reviews = min(reviews, remaining)
    remaining -= reviews
    no_action = min(no_action, remaining)
    remaining -= no_action
    detail_needed = min(detail_needed, remaining)
    payload = {
        "scope": "all_participating_workspaces",
        "workspaces": len(directories),
        "systems_monitored": systems,
        "evaluations_performed": evaluations,
        "review_events_created": reviews,
        "apps_needing_review": len(apps_needing_review),
        "outcomes_recorded": outcomes,
        "no_action_evaluations": no_action,
        "detail_needed_evaluations": detail_needed,
        "last_activity": datetime.fromtimestamp(last_activity, timezone.utc).isoformat(),
        "updated_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "privacy": (
            "Anonymous totals only. App names, account details, evidence, "
            "and source URLs are never included."
        ),
    }
    table.put_item(
        Item={
            "pk": "GLOBAL",
            "sk": "impact",
            "payload": json.dumps(payload),
            "expires_at": Decimal(str(now + PUBLIC_IMPACT_TTL)),
        }
    )
    return payload


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


def monitoring_schedule(enabled: bool, now: datetime | None = None) -> dict[str, Any]:
    zone = ZoneInfo("America/Toronto")
    local = (now or datetime.now(timezone.utc)).astimezone(zone)
    next_check = local.replace(hour=7, minute=0, second=0, microsecond=0)
    if next_check <= local:
        next_check += timedelta(days=1)
    return {
        "timezone": "America/Toronto",
        "hour": 7,
        "next_check_at": next_check.astimezone(timezone.utc).isoformat() if enabled else None,
    }


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
            preferences = store.get("preferences") or {}
            data["account"] = {
                "automatic_checks": preferences.get("automatic_checks", True),
                "viewer_lens": preferences.get("viewer_lens", "business"),
            }
            data["monitoring"]["schedule"] = monitoring_schedule(
                data["account"]["automatic_checks"]
            )
            result = response(200, data)
        return result
    # Recording a human outcome is independent of source scanning. Keep it
    # available while the worker is running so a finding can be closed without
    # making the user wait or leaving the modal in a misleading error state.
    lock = None
    if not (path == "/api/dispositions" and method == "POST"):
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
            from .models import AgentReview, AgentReviewOutcome, SystemPassport
            from .web_api import MAX_WEB_SYSTEMS, workspace

            system_id = body.get("system_id", "")
            if not re.fullmatch(r"agent-[a-f0-9-]{12}", system_id):
                return response(400, {"error": "Invalid connection system"})
            # Validate the profile and the review before writing either: a 400 must mean
            # nothing was applied, or a retrying agent cannot tell what was saved.
            profile = review = None
            if "profile" in body:
                try:
                    profile = SystemPassport.model_validate(body["profile"]).stamp_architecture()
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
                        # A daily agent sync rarely resends the backend map; keep it.
                        profile = profile.keep_architecture_from(existing)
                    if not profile.source_agent:
                        profile.source_agent = "Connected project agent"
                except (ValueError, TypeError) as exc:
                    return response(
                        400, {"error": "Send a valid system profile", "detail": _first_error(exc)}
                    )
            if "review" in body:
                try:
                    review = AgentReview.model_validate({**body["review"], "system_id": system_id})
                    finding = store.get_finding(review.finding_id)
                    if not finding or finding.system_id != system_id:
                        raise ValueError("Review must match a finding for the connected app")
                    if review.outcome == AgentReviewOutcome.APP_UPDATED and profile is None:
                        raise ValueError("An app-updated review must include the updated profile")
                except (ValueError, TypeError):
                    return response(400, {"error": "Send a valid review result"})
            if profile is not None:
                store.upsert_system(profile)
            if review is not None:
                store.put("agent-review#" + system_id, review.model_dump(mode="json"))
            result = workspace(store, settings)
            return response(
                200,
                {
                    "system": next((x for x in result["systems"] if x["id"] == system_id), None),
                    "findings": [x for x in result["findings"] if x["system_id"] == system_id],
                    "review": store.get("agent-review#" + system_id),
                    "sources": result["sources"],
                    "latest_check": (
                        {k: result["runs"][0][k] for k in ("started_at", "status", "source_health")}
                        if result["runs"]
                        else None
                    ),
                    "next_sync": "After midnight UTC tomorrow",
                    **(
                        {"backend_map_request": BACKEND_MAP_REQUEST}
                        if (saved := store.get_system(system_id)) and saved.architecture is None
                        else {}
                    ),
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
        if lock:
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
        if settings.inference_mode == "bedrock" and not reserve_budget(store.table, month):
            store.put(
                "job",
                {
                    **job,
                    "status": "paused",
                    "message": ("The workspace check limit is temporarily full. Try again later."),
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
            if settings.inference_mode == "bedrock":
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
