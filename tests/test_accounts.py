from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from decimal import Decimal
from types import SimpleNamespace

import boto3
import pytest
from conftest import make_finding
from moto import mock_aws

from builtwatch.accounts import public_impact, reserve_budget, serve, settle_budget, verify, work
from builtwatch.config import Settings
from builtwatch.dynamo_store import DynamoStore, tenant_id
from builtwatch.models import ScanRun


@pytest.fixture
def table():
    with mock_aws():
        yield boto3.resource("dynamodb", region_name="us-east-1").create_table(
            TableName="test-accounts",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": key, "KeyType": kind}
                for key, kind in [("pk", "HASH"), ("sk", "RANGE")]
            ],
            AttributeDefinitions=[
                {"AttributeName": key, "AttributeType": "S"} for key in ["pk", "sk"]
            ],
        )


def event(path="/api/workspace", method="GET", body=""):
    return {"rawPath": path, "requestContext": {"http": {"method": method}}, "body": body}


def signed(account, secret="test-secret", stamp=None):
    result = event()
    stamp = str(stamp or int(time.time()))
    nonce = str(uuid.uuid4())
    message = "\n".join(
        ["GET", "/api/workspace", account, stamp, nonce, hashlib.sha256(b"").hexdigest()]
    )
    signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    result["headers"] = {
        "x-bw-account": account,
        "x-bw-time": stamp,
        "x-bw-nonce": nonce,
        "x-bw-signature": signature,
    }
    return result


def test_signature_auth_replay_and_tampering(table):
    account = tenant_id("alice")
    request = signed(account)
    assert verify(request, "test-secret", table) == account
    assert verify(request, "test-secret", table) is None
    for alteration in ["body", "tenant", "path", "old", "secret"]:
        request = signed(account, stamp=int(time.time()) - 301 if alteration == "old" else None)
        if alteration == "body":
            request["body"] = '{"stolen":true}'
        if alteration == "tenant":
            request["headers"]["x-bw-account"] = tenant_id("bob")
        if alteration == "path":
            request["rawPath"] = "/api/systems"
        assert verify(request, "bad" if alteration == "secret" else "test-secret", table) is None


def test_public_impact_returns_aggregate_totals_without_workspace_details(table, passport):
    store = DynamoStore(table, tenant_id("impact-user"))
    store.upsert_system(passport)
    store.put(
        "run#impact",
        {
            "status": "complete",
            "systems_evaluated": [passport.id],
            "evaluations_performed": 3,
            "review_events_created": 1,
            "no_action_evaluations": 1,
            "detail_needed_evaluations": 1,
            "finished_at": "2026-09-11T12:00:00+00:00",
        },
    )
    result = public_impact(table)
    assert result["workspaces"] == 1
    assert result["systems_monitored"] == 1
    assert result["evaluations_performed"] == 3
    assert result["review_events_created"] == 1
    assert "email" not in json.dumps(result).lower()
    assert "system_id" not in json.dumps(result)
    assert table.get_item(Key={"pk": "GLOBAL", "sk": "impact"}).get("Item")


def test_accounts_cannot_read_delete_or_dispose_each_others_records(table, passport, snapshot):
    alice, bob = [DynamoStore(table, tenant_id(name)) for name in ["alice", "bob"]]
    alice.upsert_system(passport)
    finding, _ = alice.save_finding(make_finding(passport, snapshot))
    assert not bob.list_systems()
    assert bob.get_finding(finding.id) is None
    assert not bob.delete_system(passport.id)
    assert alice.get_system(passport.id)
    result = serve(
        event(
            "/api/dispositions",
            "POST",
            json.dumps({"finding_id": finding.id, "action": "acknowledged"}),
        ),
        bob,
        Settings(),
        None,
    )
    assert result["statusCode"] == 404
    bob.upsert_system(passport.model_copy(update={"name": "Bob only"}))
    assert alice.get_system(passport.id).name != bob.get_system(passport.id).name


def test_api_readable_during_worker_lock_writes_blocked(table, passport):
    store = DynamoStore(table, tenant_id("alice"))
    store.upsert_system(passport)
    assert store.acquire_lock("worker")
    assert serve(event(), store, Settings(), None)["statusCode"] == 200
    assert (
        serve(event("/api/systems/" + passport.id, "DELETE"), store, Settings(), None)["statusCode"]
        == 409
    )
    store.release_lock("worker")
    assert (
        serve(event("/api/systems/" + passport.id, "DELETE"), store, Settings(), None)["statusCode"]
        == 200
    )


def test_shared_budget_is_bounded(table):
    assert all(reserve_budget(table, "2026-09") for _ in range(5))
    assert not reserve_budget(table, "2026-09")
    settle_budget(table, "2026-09", 0.01)
    assert not reserve_budget(table, "2026-09")
    settle_budget(table, "2026-09", 0.01)
    assert reserve_budget(table, "2026-09")
    assert reserve_budget(table, "2026-10")


def test_enqueue_and_worker_are_idempotent(table, passport):
    store = DynamoStore(table, tenant_id("alice"))
    store.upsert_system(passport)
    jobs = []
    assert (
        serve(event("/api/scan", "POST", "{}"), store, Settings(), jobs.append)["statusCode"] == 202
    )
    assert (
        serve(event("/api/scan", "POST", "{}"), store, Settings(), jobs.append)["statusCode"] == 429
    )
    calls = []

    def scan(*args, **kwargs):
        calls.append(True)
        return SimpleNamespace(
            run=ScanRun(id="run-test", mode="live", status="complete", estimated_cost_usd=0.02),
            summary_line=lambda: "Finished",
        )

    assert work(jobs[0], store, Settings(), scan)["status"] == "complete"
    assert work(jobs[0], store, Settings(), scan)["status"] == "skipped"
    assert len(calls) == 1
    assert store.acquire_lock("next")
    allocated = table.get_item(Key={"pk": "BUDGET", "sk": time.strftime("%Y-%m", time.gmtime())})[
        "Item"
    ]["allocated"]
    assert allocated == Decimal("0.02")


def test_failed_enqueue_can_retry(table, passport):
    store = DynamoStore(table, tenant_id("alice"))
    store.upsert_system(passport)

    def fail(*args):
        raise RuntimeError("Unavailable")

    with pytest.raises(RuntimeError):
        serve(event("/api/scan", "POST", "{}"), store, Settings(), fail)
    assert store.job()["status"] == "failed"
    assert (
        serve(event("/api/scan", "POST", "{}"), store, Settings(), lambda x: None)["statusCode"]
        == 202
    )


def test_dynamo_retains_history_and_current_revision(table, passport, snapshot):
    store = DynamoStore(table, tenant_id("alice"))
    store.upsert_system(passport)
    store.add_snapshot(snapshot)
    first, new = store.save_finding(make_finding(passport, snapshot, finding_id="first"))
    assert new
    same, new = store.save_finding(make_finding(passport, snapshot, finding_id="second"))
    assert not new and same.id == first.id
    store.save_finding(
        make_finding(passport, snapshot, finding_id="changed", facts=["New material requirement"])
    )
    assert store.list_findings()[0].id == "changed"
    assert len(store.list_findings(current_only=False)) == 2
    assert store.get_snapshot(snapshot.id).content == snapshot.content
    store.mark_assessed("pair")
    assert store.assessed("pair")
    store.record_cost("run", "model", 1, 1, 0.02)
    store.record_cost("run", "model", 1, 1, 0.02)
    assert store.spent_today() == 0.02


def test_pilot_enrollment_is_capped_and_existing_accounts_keep_access(table):
    from builtwatch.admission import admit

    for i in range(25):
        assert admit(table, tenant_id(f"user-{i}"))
    assert not admit(table, tenant_id("over-capacity"))
    assert admit(table, tenant_id("user-0"))


def test_daily_allowance_stops_work(table):
    from builtwatch.admission import allow_request

    for _ in range(3):
        assert allow_request(table, tenant_id("a"), limit=3)
    assert not allow_request(table, tenant_id("a"), limit=3)
    assert allow_request(table, tenant_id("b"), limit=3)


def test_intake_is_reviewable_and_does_not_silently_save(table, passport):
    from builtwatch.web_intake import draft_profile

    store = DynamoStore(table, tenant_id("intake-user"))
    jobs = []
    r = serve(
        event(
            "/api/intake",
            "POST",
            json.dumps(
                {
                    "description": "A workflow that drafts Gmail replies for a person to approve.",
                    "source_agent": "Project coding agent",
                }
            ),
        ),
        store,
        Settings(),
        jobs.append,
    )
    assert r["statusCode"] == 202
    assert not store.list_systems()

    def extract(description, settings, meter, system_id):
        meter.record(settings.assess_model_id, 100, 50)
        return passport.model_copy(update={"id": system_id})

    assert draft_profile(jobs[0], store, Settings(), extract)["status"] == "complete"
    assert store.get("intake-draft")["profile"]["name"] == passport.name
    assert store.get("intake-draft")["profile"]["source_agent"] == "Project coding agent"
    assert not store.list_systems()
    assert store.get("intake-input") is None
    assert store.spent_today() > 0
    assert draft_profile(jobs[0], store, Settings(), extract)["status"] == "skipped"


def test_intake_failure_removes_input_and_records_cost(table):
    from builtwatch.web_intake import draft_profile

    store = DynamoStore(table, tenant_id("failed-intake"))
    jobs = []
    serve(
        event(
            "/api/intake",
            "POST",
            json.dumps({"description": "A workflow that sends approved emails through Gmail."}),
        ),
        store,
        Settings(),
        jobs.append,
    )

    def extract(description, settings, meter, system_id):
        meter.record(settings.assess_model_id, 100, 50)
        raise ValueError("Malformed model output")

    with pytest.raises(ValueError):
        draft_profile(jobs[0], store, Settings(), extract)
    assert store.job()["status"] == "failed"
    assert store.get("intake-input") is None
    assert store.get("intake-draft") is None
    assert store.spent_today() > 0
    assert store.acquire_lock("released")


def test_summary_update_preserves_identity_and_requires_review(table, passport):
    from builtwatch.web_intake import draft_profile

    store = DynamoStore(table, tenant_id("update-user"))
    store.upsert_system(passport)
    jobs = []
    r = serve(
        event(
            "/api/intake",
            "POST",
            json.dumps(
                {
                    "system_id": passport.id,
                    "description": "Local-only workflow. Email sending is now disabled.",
                }
            ),
        ),
        store,
        Settings(),
        jobs.append,
    )
    assert r["statusCode"] == 202

    def extract(description, settings, meter, system_id):
        assert "Previous confirmed profile" in description
        assert "Email sending is now disabled" in description
        return passport.model_copy(update={"id": system_id, "purpose": "Local only"})

    draft_profile(jobs[0], store, Settings(), extract)
    draft = store.get("intake-draft")["profile"]
    assert draft["id"] == passport.id
    assert draft["purpose"] == "Local only"
    assert store.get_system(passport.id).purpose == passport.purpose


def test_repeated_single_import_matches_existing_app_by_name(table, passport):
    """A second plain-text import refreshes the app instead of creating a duplicate."""
    from builtwatch.web_intake import draft_profile

    store = DynamoStore(table, tenant_id("repeat-import-user"))
    store.upsert_system(passport)
    jobs = []
    result = serve(
        event(
            "/api/intake",
            "POST",
            json.dumps(
                {
                    "description": "A refreshed summary for the same app with updated limits.",
                    "source_agent": "Project coding agent",
                }
            ),
        ),
        store,
        Settings(),
        jobs.append,
    )
    assert result["statusCode"] == 202

    def extract(description, settings, meter, system_id):
        meter.record(settings.assess_model_id, 100, 50)
        return passport.model_copy(
            update={"id": system_id, "purpose": "Updated purpose from the agent"}
        )

    assert draft_profile(jobs[0], store, Settings(), extract)["status"] == "complete"
    draft = store.get("intake-draft")["profile"]
    assert draft["id"] == passport.id
    assert draft["purpose"] == "Updated purpose from the agent"


def test_intake_cannot_update_another_accounts_system(table, passport):
    store = DynamoStore(table, tenant_id("missing-system"))
    r = serve(
        event(
            "/api/intake",
            "POST",
            json.dumps(
                {
                    "system_id": passport.id,
                    "description": "Use this summary to update another account system.",
                }
            ),
        ),
        store,
        Settings(),
        lambda x: None,
    )
    assert r["statusCode"] == 404


def test_account_routes_accept_encoded_json_and_reject_nonobjects(table):
    import base64

    store = DynamoStore(table, tenant_id("encoded-user"))
    request = event(
        "/api/preferences", "POST", base64.b64encode(b'{"automatic_checks":false}').decode()
    )
    request["isBase64Encoded"] = True
    assert serve(request, store, Settings(), None)["statusCode"] == 200
    assert store.get("preferences")["automatic_checks"] is False
    assert serve(event("/api/intake", "POST", "[]"), store, Settings(), None)["statusCode"] == 400


def test_agent_sync_registers_one_profile_without_model_and_scopes_response(table, snapshot):
    from builtwatch.models import SystemPassport

    store = DynamoStore(table, tenant_id("agent-owner"))
    other = SystemPassport(id="other-app", name="Other", purpose="Unrelated private app")
    store.upsert_system(other)
    profile = SystemPassport(id="agent-12345678-123", name="Connected", purpose="Draft replies")
    calls = []
    result = serve(
        event(
            "/api/agent/sync",
            "POST",
            json.dumps(
                {
                    "system_id": profile.id,
                    "profile": profile.model_dump(mode="json"),
                }
            ),
        ),
        store,
        Settings(),
        calls.append,
    )
    assert result["statusCode"] == 200
    payload = json.loads(result["body"])
    assert payload["system"]["id"] == profile.id
    assert payload["system"]["source_agent"] == "Connected project agent"
    assert "Other" not in result["body"]
    assert not calls
    assert store.get_system(other.id) is not None
    finding, _ = store.save_finding(make_finding(profile, snapshot, finding_id="find-agent"))
    review_result = serve(
        event(
            "/api/agent/sync",
            "POST",
            json.dumps(
                {
                    "system_id": profile.id,
                    "review": {
                        "finding_id": finding.id,
                        "outcome": "no_change_needed",
                        "summary": "The project does not use the affected feature.",
                    },
                }
            ),
        ),
        store,
        Settings(),
        calls.append,
    )
    assert review_result["statusCode"] == 200
    pending = store.get("agent-review#" + profile.id)
    assert pending["outcome"] == "no_change_needed"
    agent_response = json.loads(review_result["body"])
    assert agent_response["findings"][0]["id"] == finding.id
    assert agent_response["review"]["finding_id"] == finding.id
    workspace = json.loads(serve(event(), store, Settings(), calls.append)["body"])
    assert workspace["agent_reviews"][0]["finding_id"] == finding.id
    assert store.get("agent-review#" + profile.id)["summary"].startswith("The project")
    disposition = serve(
        event(
            "/api/dispositions",
            "POST",
            json.dumps({"finding_id": finding.id, "action": "acknowledged"}),
        ),
        store,
        Settings(),
        calls.append,
    )
    assert disposition["statusCode"] == 200
    assert store.get("agent-review#" + profile.id) is None
    bad = serve(
        event(
            "/api/agent/sync",
            "POST",
            json.dumps(
                {
                    "system_id": profile.id,
                    "profile": other.model_dump(mode="json"),
                }
            ),
        ),
        store,
        Settings(),
        calls.append,
    )
    assert bad["statusCode"] == 400

    updated_without_profile = serve(
        event(
            "/api/agent/sync",
            "POST",
            json.dumps(
                {
                    "system_id": profile.id,
                    "review": {
                        "finding_id": finding.id,
                        "outcome": "app_updated",
                        "summary": "Updated the dependency.",
                    },
                }
            ),
        ),
        store,
        Settings(),
        calls.append,
    )
    assert updated_without_profile["statusCode"] == 400


def test_cost_guard_fails_closed(table, monkeypatch):
    import time

    monkeypatch.setenv("BW_COST_GUARD_REQUIRED", "true")
    assert not reserve_budget(table, "2026-09")
    for paused, checked in [(True, int(time.time())), (False, int(time.time()) - 172801)]:
        table.put_item(
            Item={"pk": "ADMIN", "sk": "snapshot", "paused": paused, "checked_at": checked}
        )
        assert not reserve_budget(table, "2026-09")
    table.put_item(
        Item={"pk": "ADMIN", "sk": "snapshot", "paused": False, "checked_at": int(time.time())}
    )
    table.put_item(Item={"pk": "ADMIN", "sk": "control", "paused": True})
    assert not reserve_budget(table, "2026-09")
    table.put_item(Item={"pk": "ADMIN", "sk": "control", "paused": False})
    assert reserve_budget(table, "2026-09")


def test_view_preference_preserves_monitoring_and_cannot_grant_access(table):
    store = DynamoStore(table, tenant_id("view-user"))
    store.put("preferences", {"automatic_checks": False, "viewer_lens": "business"})
    result = serve(
        event("/api/preferences", "POST", '{"viewer_lens":"operations"}'), store, Settings(), None
    )
    assert result["statusCode"] == 200
    assert store.get("preferences") == {"automatic_checks": False, "viewer_lens": "operations"}
    data = json.loads(serve(event(), store, Settings(), None)["body"])
    assert data["account"]["viewer_lens"] == "operations"
    result = serve(
        event("/api/preferences", "POST", '{"viewer_lens":"admin"}'), store, Settings(), None
    )
    assert result["statusCode"] == 400
    assert store.get("preferences")["viewer_lens"] == "operations"
    result = serve(
        event("/api/preferences", "POST", '{"automatic_checks":true}'), store, Settings(), None
    )
    assert result["statusCode"] == 200
    assert store.get("preferences")["viewer_lens"] == "operations"
    assert store.get("preferences")["automatic_checks"] is True
