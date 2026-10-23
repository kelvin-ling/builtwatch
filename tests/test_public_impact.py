"""The public Impact totals: fast to compute, and in step with what workspaces show."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from conftest import make_finding

from builtwatch.accounts import public_impact, serve
from builtwatch.config import Settings
from builtwatch.dynamo_store import DynamoStore, tenant_id
from builtwatch.models import Disposition, SourceSnapshot
from builtwatch.quality import QUALITY_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _items_read(table):
    """Count every item DynamoDB returns to queries, whichever interface made them."""
    seen = {"items": 0}

    def count(parsed, **_):
        seen["items"] += len(parsed.get("Items", []))

    table.meta.client.meta.events.register("after-call.dynamodb.Query", count)
    return seen


def _open_reviews(store):
    event = {"rawPath": "/api/workspace", "requestContext": {"http": {"method": "GET"}}}
    data = json.loads(serve(event, store, Settings(), None)["body"])
    return {
        f["system_id"]
        for f in data["findings"]
        if f["relevance"] == "relevant" and f["disposition"] == "open"
    }


def test_totals_never_read_page_snapshots(table, passport, snapshot):
    store = DynamoStore(table, tenant_id("busy-workspace"))
    store.upsert_system(passport)
    store.put(
        "run#one",
        {"status": "complete", "evaluations_performed": 4, "finished_at": "2026-10-23T11:00:00Z"},
    )
    finding, _ = store.save_finding(make_finding(passport, snapshot))
    store.add_disposition(Disposition(id="disp_1", finding_id=finding.id, action="acknowledged"))
    # Two months of daily checks: a full page per day, plus check bookkeeping.
    page = "Changelog entry. " * 2000
    for day in range(60):
        store.add_snapshot(
            SourceSnapshot(id=f"snap_{day:03d}", source_id=snapshot.source_id, content=page)
        )
        store.mark_assessed(f"pair-{day}")

    reads = _items_read(table)
    result = public_impact(table, Settings())

    # One directory entry, then only the four counted record families: 1 app, 1 check,
    # 1 review and 1 outcome. Snapshots, latest pages and assessment marks stay unread.
    assert reads["items"] == 5
    assert result["systems_monitored"] == 1
    assert result["evaluations_performed"] == 4
    assert result["outcomes_recorded"] == 1
    assert result["apps_needing_review"] == 0
    assert result["last_activity"].startswith("2026-10-23T11:00")


def test_systems_needing_review_match_what_each_workspace_shows(table, passport, snapshot):
    store = DynamoStore(table, tenant_id("owner"))
    billing = passport.model_copy(update={"id": "billing", "name": "Billing", "services": []})
    support = passport.model_copy(update={"id": "support", "name": "Support"})
    for app in (passport, billing, support):
        store.upsert_system(app)

    # inbox-triage: every relevant record is one the desk no longer shows as open.
    old_rules = make_finding(passport, snapshot, finding_id="find_old", development_key="old")
    old_rules.quality_version = QUALITY_VERSION - 1  # superseded assessment rules
    store.put("finding#find_old", old_rules.model_dump(mode="json"))
    earlier = make_finding(passport, snapshot, finding_id="find_v1", development_key="dev")
    earlier.created_at -= timedelta(days=2)
    store.put("finding#find_v1", earlier.model_dump(mode="json"))
    latest = make_finding(
        passport, snapshot, finding_id="find_v2", development_key="dev", facts=["Revised."]
    )
    store.save_finding(latest)
    store.add_disposition(
        Disposition(id="disp_v2", finding_id="find_v2", action="dismissed", reason="Under limit.")
    )
    # billing: an older product match the current matching rules withhold.
    withheld = make_finding(
        billing,
        snapshot,
        finding_id="find_stripe",
        development_key="stripe",
        passage="The Charges API is deprecated in favour of PaymentIntents.",
    )
    withheld.source_id = "stripe-upgrades"
    withheld.assessment_method = "rules-v2"
    store.save_finding(withheld)
    # A review left behind by an app that was later removed from the workspace.
    store.put(
        "finding#find_gone",
        make_finding(
            passport.model_copy(update={"id": "removed-app"}), snapshot, finding_id="find_gone"
        ).model_dump(mode="json"),
    )
    # support: one current, open, relevant review.
    store.save_finding(make_finding(support, snapshot, finding_id="find_live"))

    assert _open_reviews(store) == {"support"}
    assert public_impact(table, Settings())["apps_needing_review"] == 1


def test_totals_add_up_across_workspaces(table, passport, snapshot):
    for name in ("alice", "bob", "carol"):
        store = DynamoStore(table, tenant_id(name))
        store.upsert_system(passport)
        store.save_finding(make_finding(passport, snapshot))
        store.put(
            "run#daily",
            {"status": "complete", "evaluations_performed": 3, "review_events_created": 1},
        )
    store.put("run#running", {"status": "running", "evaluations_performed": 50})

    result = public_impact(table, Settings())

    assert result["workspaces"] == 3
    assert result["systems_monitored"] == 3
    assert result["evaluations_performed"] == 9
    assert result["review_events_created"] == 3
    assert result["apps_needing_review"] == 3
    assert "alice" not in json.dumps(result)


def test_a_public_read_does_not_load_the_scan_pipeline():
    """API cold starts skip the scan pipeline and the agent SDK; only the worker needs them."""
    code = (
        "import sys, accounts_runner; "
        "print(sorted(m for m in ('builtwatch.pipeline', 'strands') if m in sys.modules))"
    )
    env_path = f"{ROOT / 'infra'}:{ROOT / 'src'}"
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={"PYTHONPATH": env_path, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "[]"
