"""The watch pipeline.

One pass: fetch the curated sources, notice which ones actually changed, screen each
(system, change) pair cheaply, investigate the survivors properly, and store findings
under a dedup key so a repeat run stays quiet.

Two properties this file exists to guarantee:

* A source that failed to fetch is recorded as a coverage failure. It can never be
  mistaken for "we checked and nothing changed".
* A finding whose substance has not changed since a previous run is not re-notified,
  and one the user already acknowledged or dismissed stays down.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .agent.relevance import assess, screen
from .config import BudgetExceeded, CostMeter, Settings
from .models import (
    Finding,
    Relevance,
    ScanRun,
    Source,
    SourceHealth,
    SourceSnapshot,
)
from .quality import QUALITY_VERSION
from .registry import enabled_sources, load_registry
from .store import Store, new_id

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    run: ScanRun
    new_findings: list[Finding] = field(default_factory=list)
    suppressed_duplicates: list[Finding] = field(default_factory=list)
    not_relevant: list[Finding] = field(default_factory=list)
    insufficient: list[Finding] = field(default_factory=list)
    screened_out: int = 0
    grounding_problems: list[str] = field(default_factory=list)

    @property
    def coverage_failures(self) -> list[SourceHealth]:
        return self.run.sources_failed

    def summary_line(self) -> str:
        if self.run.status == "aborted":
            return f"Scan aborted: {self.run.abort_reason}"
        parts = [f"{len(self.new_findings)} new finding(s)"]
        if self.suppressed_duplicates:
            parts.append(f"{len(self.suppressed_duplicates)} already reported")
        if self.insufficient:
            parts.append(f"{len(self.insufficient)} need more information")
        if self.coverage_failures:
            parts.append(f"{len(self.coverage_failures)} SOURCE(S) COULD NOT BE CHECKED")
        return "; ".join(parts)


def collect_snapshots(
    store: Store, sources: list[Source], mode: str, settings: Settings, run: ScanRun
) -> dict[str, SourceSnapshot]:
    """Fetch every source, record health, and return only the ones that changed."""
    from .fetch import fetch

    changed: dict[str, SourceSnapshot] = {}
    for source in sources:
        previous = store.latest_snapshot(source.id)
        previous_hash = previous.content_hash if previous and previous.mode == mode else None
        snapshot = fetch(source, mode, settings.replay_dir, settings.limits)
        if previous_hash and snapshot.succeeded:
            differences = list(
                difflib.unified_diff(
                    previous.content.splitlines(),
                    snapshot.content.splitlines(),
                    fromfile="previous observation",
                    tofile="current observation",
                    lineterm="",
                )
            )
            snapshot.change_context = (
                "Observed page difference (untrusted data):\n" + "\n".join(differences)[:8000]
            )
        store.add_snapshot(snapshot)

        health = SourceHealth(
            source_id=source.id,
            fetch_status=snapshot.fetch_status,
            http_status=snapshot.http_status,
            error=snapshot.error,
            snapshot_id=snapshot.id,
        )
        if snapshot.succeeded:
            health.changed = snapshot.content_hash != previous_hash
            changed[snapshot.id] = snapshot
        else:
            logger.warning(
                "coverage failure on %s: %s (%s)",
                source.id,
                snapshot.fetch_status.value,
                snapshot.error,
            )
        run.source_health.append(health)
    return changed


def run_scan(
    store: Store,
    settings: Settings,
    mode: str = "replay",
    system_ids: list[str] | None = None,
    force_reassess: bool = False,
) -> ScanResult:
    """Execute one complete watch pass."""
    limits = settings.limits
    sources = enabled_sources(load_registry(settings.registry_path))[: limits.max_sources_per_run]
    source_map = {s.id: s for s in sources}

    systems = store.list_systems()
    if system_ids:
        systems = [s for s in systems if s.id in set(system_ids)]
    systems = systems[: limits.max_systems_per_run]

    run = ScanRun(
        id=new_id("run"),
        mode=mode,  # type: ignore[arg-type]
        model_id=settings.assess_model_id,
        systems_evaluated=[s.id for s in systems],
    )
    store.save_run(run)
    result = ScanResult(run=run)

    meter = CostMeter(
        settings, spent_today=store.spent_today(), spent_month=store.spent_this_month()
    )

    changed = collect_snapshots(store, sources, mode, settings, run)
    logger.info(
        "%s source(s) checked, %s changed, %s failed",
        len(sources),
        len(changed),
        len(run.sources_failed),
    )

    if not systems:
        run.status = "complete"
        run.finished_at = datetime.now(timezone.utc)
        store.save_run(run)
        return result

    try:
        for passport in systems:
            for snapshot_id, snapshot in changed.items():
                source = source_map.get(snapshot.source_id)
                if source is None:
                    continue

                # A source hash alone misses new/edited systems and skips aborted pairs.
                profile_hash = hashlib.sha256(
                    json.dumps(
                        passport.model_dump(mode="json", exclude={"updated_at", "created_at"}),
                        sort_keys=True,
                    ).encode()
                ).hexdigest()
                pair_key = (
                    f"quality-v{QUALITY_VERSION}:{passport.id}:{profile_hash}"
                    f":{mode}:{source.id}:{snapshot.content_hash}"
                )
                if store.assessed(pair_key) and not force_reassess:
                    continue
                verdict = screen(passport, snapshot, source, settings, meter)
                if verdict.plausible == "no":
                    store.mark_assessed(pair_key)
                    result.screened_out += 1
                    logger.debug("screened out %s x %s: %s", passport.id, source.id, verdict.reason)
                    continue

                finding, problems = assess(
                    passport=passport,
                    snapshots={snapshot_id: snapshot},
                    sources={source.id: source},
                    scan_run_id=run.id,
                    settings=settings,
                    meter=meter,
                )
                if problems:
                    result.grounding_problems.extend(
                        f"{passport.id}/{source.id}: {p}" for p in problems
                    )
                if finding is None:
                    raise RuntimeError("Assessment incomplete: " + "; ".join(problems))

                finding.quality_version = QUALITY_VERSION
                stored, is_new = store.save_finding(finding)
                if not problems:
                    store.mark_assessed(pair_key)
                if not is_new:
                    result.suppressed_duplicates.append(stored)
                elif stored.relevance is Relevance.RELEVANT:
                    result.new_findings.append(stored)
                elif stored.relevance is Relevance.INSUFFICIENT_INFORMATION:
                    result.insufficient.append(stored)
                else:
                    result.not_relevant.append(stored)

        run.status = "complete"
    except BudgetExceeded as exc:
        run.status = "aborted"
        run.abort_reason = str(exc)
        logger.error("scan aborted on budget: %s", exc)
    except Exception as exc:
        # Any unexpected failure must leave the run visibly aborted. A run stuck at
        # "running" is indistinguishable from one still in flight, which is precisely
        # the ambiguity this product exists to eliminate. The exception is recorded and
        # re-raised context is preserved in the reason.
        run.status = "aborted"
        run.abort_reason = f"{type(exc).__name__}: {exc}"
        logger.exception("scan aborted on unexpected error")

    run.validation_failures = len(result.grounding_problems)
    run.input_tokens = meter.input_tokens
    run.output_tokens = meter.output_tokens
    run.estimated_cost_usd = meter.run_cost
    run.finished_at = datetime.now(timezone.utc)
    store.save_run(run)
    if meter.run_cost > 0:
        store.record_cost(
            run.id,
            settings.assess_model_id,
            meter.input_tokens,
            meter.output_tokens,
            meter.run_cost,
        )
    return result
