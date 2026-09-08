"""Scheduled watch runner.

One entrypoint, two deployment shapes:

* ``lambda_handler`` — AWS Lambda behind EventBridge Scheduler. Cheapest path: no idle
  cost, no container, sub-second cold start on the Python runtime.
* ``invoke`` — plain callable, used by the Bedrock AgentCore Runtime entrypoint and by
  anyone running the pipeline from their own scheduler or from cron.

Both return the same JSON summary, and both are deliberately non-fatal: a scan that fails
returns a structured error rather than throwing, so the scheduler records a result instead
of a retry storm.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from builtwatch.config import Settings
from builtwatch.pipeline import run_scan
from builtwatch.store import Store

logging.basicConfig(level=os.environ.get("BW_LOG_LEVEL", "INFO"))
logger = logging.getLogger("builtwatch.runner")


def _settings_for_lambda() -> Settings:
    """Lambda's only writable location is /tmp, and it does not persist between runs.

    For a real deployment BW_DB should point at an EFS mount or the Store should be
    swapped for the DynamoDB backend. Defaulting to /tmp keeps a cold deploy runnable,
    but a cold database means every finding looks new — so we say so, loudly.
    """
    settings = Settings()
    if "BW_DB" not in os.environ:
        settings.db_path = Path("/tmp/builtwatch.db")
        logger.warning(
            "BW_DB is unset; using ephemeral /tmp storage. Dedup and disposition history "
            "will not survive between invocations."
        )
    return settings


def invoke(
    mode: str = "live",
    system_ids: list[str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Run one watch pass and return a JSON-serialisable summary."""
    settings = settings or _settings_for_lambda()
    store = Store(settings.db_path)
    try:
        result = run_scan(store, settings, mode=mode, system_ids=system_ids)
        return {
            "run_id": result.run.id,
            "status": result.run.status,
            "mode": result.run.mode,
            "summary": result.summary_line(),
            "new_findings": [
                {
                    "id": f.id,
                    "system_id": f.system_id,
                    "title": f.title,
                    "adoption_status": f.adoption_status.value,
                    "development_key": f.development_key,
                }
                for f in result.new_findings
            ],
            "needs_information": len(result.insufficient),
            "suppressed_duplicates": len(result.suppressed_duplicates),
            "screened_out": result.screened_out,
            # Coverage failures are top-level, not buried in a detail field. A caller
            # that ignores everything else must still trip over them.
            "coverage_complete": result.run.coverage_complete,
            "coverage_failures": [
                {"source_id": h.source_id, "status": h.fetch_status.value, "error": h.error}
                for h in result.coverage_failures
            ],
            "estimated_cost_usd": round(result.run.estimated_cost_usd, 6),
            "input_tokens": result.run.input_tokens,
            "output_tokens": result.run.output_tokens,
            "abort_reason": result.run.abort_reason,
        }
    finally:
        store.close()


def lambda_handler(event: dict | None = None, context: Any = None) -> dict[str, Any]:
    """EventBridge Scheduler target."""
    event = event or {}
    mode = event.get("mode", "live")
    system_ids = event.get("system_ids")

    try:
        summary = invoke(mode=mode, system_ids=system_ids)
    except Exception as exc:
        logger.exception("watch run failed")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"{type(exc).__name__}: {exc}"}),
        }

    logger.info("watch run complete: %s", summary["summary"])
    return {"statusCode": 200, "body": json.dumps(summary)}


if __name__ == "__main__":
    import sys

    print(json.dumps(invoke(mode=sys.argv[1] if len(sys.argv) > 1 else "replay"), indent=2))
