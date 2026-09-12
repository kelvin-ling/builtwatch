"""Asynchronous Strands intake: draft, explicit human review, then ordinary save."""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from dataclasses import replace
from typing import Any

from .accounts import reserve_budget, settle_budget
from .admission import allow_request
from .config import CostMeter
from .intake import from_text
from .web_api import MAX_WEB_SYSTEMS, response

MIN_DESCRIPTION = 20
MAX_DESCRIPTION = 12000
DAILY_DRAFTS = 5


def _canonical_name(value: str) -> str:
    """Match harmless naming changes so repeat imports update instead of duplicating."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def queue_intake(store: Any, settings: Any, body: dict, invoke: Any) -> dict:
    description = body.get("description")
    if (
        not isinstance(description, str)
        or not MIN_DESCRIPTION <= len(description.strip()) <= MAX_DESCRIPTION
    ):
        return response(
            400,
            {"error": "Use a sentence or summary with 20 to 12,000 characters."},
        )
    system_id = body.get("system_id")
    source_agent = body.get("source_agent")
    if source_agent is not None and not isinstance(source_agent, str):
        return response(400, {"error": "Agent name must be text."})
    source_agent = source_agent.strip()[:120] if source_agent else None
    previous = store.get_system(system_id) if isinstance(system_id, str) else None
    if system_id is not None and previous is None:
        return response(404, {"error": "That system is not in your workspace."})
    if previous is None and len(store.list_systems()) >= MAX_WEB_SYSTEMS:
        return response(
            409, {"error": "Your workspace has 10 systems. Remove one before adding another."}
        )
    description_hash = hashlib.sha256(
        (str(system_id or "") + str(source_agent or "") + description.strip()).encode()
    ).hexdigest()
    existing = store.get("intake-draft") or {}
    if existing.get("description_hash") == description_hash:
        return response(200, {"ready": True})
    if store.job().get("status") in {"queued", "running"}:
        return response(409, {"error": "Please wait for your current task to finish."})
    if (
        store.spent_this_month() >= settings.limits.max_cost_per_month_usd
        or store.spent_today() >= settings.limits.max_cost_per_day_usd
    ):
        return response(
            429,
            {"error": "The assisted-drafting limit was reached. Use the optional editor or import a profile."},
        )
    if not allow_request(store.table, store.tenant, DAILY_DRAFTS, "intake"):
        return response(
            429,
            {"error": "Five drafts used today. Use the optional editor or return tomorrow."},
        )
    job = {
        "id": str(uuid.uuid4()),
        "type": "intake",
        "status": "queued",
        "requested_at": time.time(),
        "message": "Preparing your app profile. You can leave this page.",
    }
    store.put(
        "intake-input",
        {
            "description": description.strip(),
            "description_hash": description_hash,
            "system_id": system_id,
            "source_agent": source_agent,
            "job_id": job["id"],
        },
    )
    store.put("job", job)
    try:
        invoke({"task": "intake", "tenant": store.tenant, "job_id": job["id"]})
    except Exception:
        store.delete("intake-input")
        store.put(
            "job",
            {**job, "status": "failed", "message": "Your draft could not start. Please try again."},
        )
        raise
    return response(202, {"queued": True})


def draft_profile(event: dict, store: Any, settings: Any, extract: Any = from_text) -> dict:
    lock = str(uuid.uuid4())
    if not store.acquire_lock(lock):
        raise RuntimeError("Workspace is busy")
    try:
        job = store.get("job") or {}
        if job.get("id") != event.get("job_id") or job.get("status") != "queued":
            return {"status": "skipped"}
        pending = store.get("intake-input") or {}
        if pending.get("job_id") != job["id"]:
            raise RuntimeError("Draft input is unavailable")
        month = time.strftime("%Y-%m", time.gmtime())
        if not reserve_budget(store.table, month):
            store.delete("intake-input")
            store.put(
                "job",
                {
                    **job,
                    "status": "paused",
                    "message": "The assisted-drafting limit is temporarily full. Use the optional editor or try again later.",
                },
            )
            return {"status": "paused"}
        store.put(
            "job",
            {
                **job,
                "status": "running",
                "started_at": time.time(),
                "message": "The intake agent is identifying services, data, and important actions.",
            },
        )
        intake_settings = replace(
            settings,
            assess_model_id=settings.screen_model_id,
            limits=replace(settings.limits, max_cost_per_run_usd=0.02),
        )
        meter = CostMeter(
            intake_settings, spent_today=store.spent_today(), spent_month=store.spent_this_month()
        )
        try:
            previous = store.get_system(pending["system_id"]) if pending.get("system_id") else None
            if pending.get("system_id") and previous is None:
                raise ValueError("The system was removed before this update")
            description = pending["description"]
            if previous:
                description = (
                    "Previous confirmed profile: "
                    + json.dumps(previous.model_dump(mode="json"))
                    + "\nUser update (replaces conflicts; retain other confirmed facts): "
                    + description
                )
            profile = extract(
                description,
                intake_settings,
                meter,
                system_id=previous.id if previous else "app-" + uuid.uuid4().hex[:12],
            )
            if pending.get("source_agent"):
                profile.source_agent = pending["source_agent"]
            elif previous:
                profile.source_agent = previous.source_agent
            if previous:
                profile.created_at = previous.created_at
            else:
                # A plain-text import has no stable ID in its summary. Match an existing
                # profile by normalized name so importing the same app again updates it.
                match = next(
                    (
                        candidate
                        for candidate in store.list_systems()
                        if _canonical_name(candidate.name) == _canonical_name(profile.name)
                    ),
                    None,
                )
                if match:
                    profile.id = match.id
                    profile.created_at = match.created_at
            # Drafts never silently become facts in the watched inventory.
            store.put(
                "intake-draft",
                {
                    "job_id": job["id"],
                    "description_hash": pending.get("description_hash"),
                    "profile": profile.model_dump(mode="json"),
                },
            )
            store.put(
                "job",
                {
                    **job,
                    "status": "complete",
                    "message": "Your profile is ready. Review it before starting the watch.",
                },
            )
            return {"status": "complete"}
        except Exception:
            store.put(
                "job",
                {
                    **job,
                    "status": "failed",
                    "message": "Draft failed. Try a clearer summary or use the optional editor.",
                },
            )
            raise
        finally:
            store.delete("intake-input")
            store.record_cost(
                "intake-" + job["id"],
                intake_settings.assess_model_id,
                meter.input_tokens,
                meter.output_tokens,
                meter.run_cost,
            )
            settle_budget(store.table, month, meter.run_cost)
    finally:
        store.release_lock(lock)
