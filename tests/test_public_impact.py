"""The public Impact totals: fast to compute, and in step with what workspaces show."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from conftest import make_finding

from builtwatch import accounts
from builtwatch.accounts import (
    IMPACT_REFRESH_CLAIM,
    IMPACT_STALE_LIMIT,
    PUBLIC_IMPACT_TTL,
    public_impact,
    refresh_public_impact,
    serve,
)
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


def _save_totals(table, payload, age):
    """Totals as a refresh `age` seconds ago saved them."""
    now = time.time()
    table.put_item(
        Item={
            "pk": "GLOBAL",
            "sk": "impact",
            "payload": json.dumps(payload),
            "expires_at": Decimal(str(now - age + PUBLIC_IMPACT_TTL)),
        }
    )


def test_stale_totals_answer_at_once_and_ask_for_one_background_refresh(table, passport):
    store = DynamoStore(table, tenant_id("alice"))
    store.upsert_system(passport)
    _save_totals(table, {"systems_monitored": 0, "updated_at": "earlier"}, age=3600)
    requests = []

    reads = _items_read(table)
    first = public_impact(table, Settings(), lambda: requests.append("refresh"))
    second = public_impact(table, Settings(), lambda: requests.append("refresh"))

    # Both visitors get the saved totals with their own timestamp; no partition is read.
    assert first == second == {"systems_monitored": 0, "updated_at": "earlier"}
    assert reads["items"] == 0
    assert requests == ["refresh"]


def test_fresh_totals_ask_for_no_refresh(table):
    _save_totals(table, {"systems_monitored": 3}, age=60)
    requests = []

    assert public_impact(table, Settings(), lambda: requests.append(1)) == {"systems_monitored": 3}
    assert requests == []


def test_first_totals_are_computed_inline(table, passport):
    store = DynamoStore(table, tenant_id("alice"))
    store.upsert_system(passport)
    requests = []

    result = public_impact(table, Settings(), lambda: requests.append(1))

    assert result["systems_monitored"] == 1
    assert requests == []


def test_a_failed_refresh_request_still_answers_with_saved_totals(table):
    _save_totals(table, {"systems_monitored": 2}, age=3600)

    def unavailable():
        raise RuntimeError("worker invoke throttled")

    assert public_impact(table, Settings(), unavailable) == {"systems_monitored": 2}


def test_an_unfinished_refresh_claim_expires(table, monkeypatch):
    _save_totals(table, {"systems_monitored": 2}, age=3600)
    requests = []
    public_impact(table, Settings(), lambda: requests.append(1))
    later = time.time() + IMPACT_REFRESH_CLAIM + 1
    monkeypatch.setattr(accounts.time, "time", lambda: later)

    public_impact(table, Settings(), lambda: requests.append(1))

    assert requests == [1, 1]


def test_a_refresh_saves_new_totals_and_clears_the_claim(table, passport):
    _save_totals(table, {"systems_monitored": 0}, age=3600)
    public_impact(table, Settings(), lambda: None)
    DynamoStore(table, tenant_id("alice")).upsert_system(passport)

    refresh_public_impact(table, Settings())

    item = table.get_item(Key={"pk": "GLOBAL", "sk": "impact"})["Item"]
    assert "refreshing_until" not in item
    assert public_impact(table, Settings(), lambda: None)["systems_monitored"] == 1


def test_without_a_background_refresh_stale_totals_are_recomputed(table, passport):
    _save_totals(table, {"systems_monitored": 0}, age=3600)
    DynamoStore(table, tenant_id("alice")).upsert_system(passport)

    assert public_impact(table, Settings())["systems_monitored"] == 1



def test_totals_a_day_past_expiry_are_recomputed_inline(table, passport):
    _save_totals(table, {"systems_monitored": 0}, age=PUBLIC_IMPACT_TTL + IMPACT_STALE_LIMIT + 60)
    DynamoStore(table, tenant_id("alice")).upsert_system(passport)
    requests = []

    assert public_impact(table, Settings(), lambda: requests.append(1))["systems_monitored"] == 1
    assert requests == []


@pytest.fixture
def runner(table, monkeypatch):
    """The Lambda handler on the mocked table, with worker invokes recorded."""
    sys.path.insert(0, str(ROOT / "infra"))
    import accounts_runner

    invoked = []

    class Lambda:
        def invoke(self, **kwargs):
            invoked.append(json.loads(kwargs["Payload"]))

    monkeypatch.setenv("BW_TABLE", table.name)
    monkeypatch.setenv("BW_WORKER", "worker")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setattr(accounts_runner.boto3, "client", lambda name: Lambda())
    accounts_runner.invoked = invoked
    return accounts_runner


def _public_get(runner):
    event = {
        "rawPath": "/api/public-impact",
        "requestContext": {"http": {"method": "GET"}},
    }
    return runner.lambda_handler(event, None)


def test_public_read_of_stale_totals_queues_the_worker(runner, table):
    _save_totals(table, {"systems_monitored": 4}, age=3600)

    result = _public_get(runner)

    assert result["statusCode"] == 200
    assert json.loads(result["body"]) == {"systems_monitored": 4}
    assert runner.invoked == [{"task": "impact"}]


def test_worker_impact_task_saves_fresh_totals(runner, table, passport):
    _save_totals(table, {"systems_monitored": 0}, age=3600)
    DynamoStore(table, tenant_id("alice")).upsert_system(passport)

    runner.lambda_handler({"task": "impact"}, None)

    assert json.loads(_public_get(runner)["body"])["systems_monitored"] == 1
    assert runner.invoked == []


def test_a_finished_check_refreshes_public_totals(runner, table, passport, monkeypatch):
    _save_totals(table, {"systems_monitored": 0}, age=60)
    store = DynamoStore(table, tenant_id("alice"))
    store.upsert_system(passport)
    monkeypatch.setattr(runner, "work", lambda *args: {"status": "complete"})

    runner.lambda_handler({"task": "scan", "tenant": store.tenant, "job_id": "j"}, None)

    # Fresh before the check, yet the page shows the new totals without waiting 15 minutes.
    assert json.loads(_public_get(runner)["body"])["systems_monitored"] == 1


def test_a_skipped_check_leaves_public_totals_alone(runner, table, passport, monkeypatch):
    _save_totals(table, {"systems_monitored": 0}, age=60)
    store = DynamoStore(table, tenant_id("alice"))
    store.upsert_system(passport)
    monkeypatch.setattr(runner, "work", lambda *args: {"status": "skipped"})

    runner.lambda_handler({"task": "scan", "tenant": store.tenant, "job_id": "j"}, None)

    assert json.loads(_public_get(runner)["body"])["systems_monitored"] == 0
