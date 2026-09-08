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

from builtwatch.accounts import reserve_budget, serve, settle_budget, verify, work
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
    assert all(reserve_budget(table, "2026-09") for _ in range(10))
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
