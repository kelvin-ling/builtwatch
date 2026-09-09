from __future__ import annotations

import json

from builtwatch.config import Settings
from builtwatch.web_api import dispatch


def event(path, method="GET", body=None, token="owner-test-key"):
    return {
        "rawPath": path,
        "headers": {"authorization": "Bearer " + token},
        "requestContext": {"http": {"method": method}},
        "body": json.dumps(body) if body is not None else None,
    }


def test_anonymous_cannot_read_or_spend(store, monkeypatch):
    monkeypatch.setenv("BW_OWNER_TOKEN", "owner-test-key")
    calls = []
    for path, method in [("/api/workspace", "GET"), ("/api/scan", "POST")]:
        result = dispatch(
            event(path, method, {}, token="wrong"), store, Settings(), lambda: calls.append(True)
        )
        assert result["statusCode"] == 401
    assert not calls


def test_system_round_trip_and_disposition(store, passport, monkeypatch):
    monkeypatch.setenv("BW_OWNER_TOKEN", "owner-test-key")
    settings = Settings()
    data = passport.model_dump(mode="json")
    result = dispatch(event("/api/systems", "POST", data), store, settings, lambda: None)
    assert result["statusCode"] == 200
    result = dispatch(event("/api/workspace"), store, settings, lambda: None)
    assert json.loads(result["body"])["systems"][0]["name"] == passport.name
    result = dispatch(event("/api/systems/" + passport.id, "DELETE"), store, settings, None)
    assert json.loads(result["body"])["deleted"]


def test_scan_reservation_blocks_double_spend(store, passport, monkeypatch):
    monkeypatch.setenv("BW_OWNER_TOKEN", "owner-test-key")
    store.upsert_system(passport)
    calls = []
    for code in [202, 429]:
        result = dispatch(
            event("/api/scan", "POST", {}), store, Settings(), lambda: calls.append(True)
        )
        assert result["statusCode"] == code
    assert len(calls) == 1


def test_invalid_profile_does_not_write(store, monkeypatch):
    monkeypatch.setenv("BW_OWNER_TOKEN", "owner-test-key")
    result = dispatch(event("/api/systems", "POST", {"id": "../../bad"}), store, Settings(), None)
    assert result["statusCode"] == 400
    assert not store.list_systems()


def test_bulk_validates_before_writes_and_updates_by_id(store, passport, monkeypatch):
    monkeypatch.setenv("BW_OWNER_TOKEN", "owner-test-key")
    p = passport.model_dump(mode="json")
    bad = {**p, "id": "../bad"}

    def send(items):
        def unexpected_model_call():
            raise AssertionError("No model calls")

        return dispatch(
            event("/api/systems/bulk", "POST", {"systems": items}),
            store,
            Settings(),
            unexpected_model_call,
        )

    assert send([p, bad])["statusCode"] == 400
    assert not store.list_systems()
    assert send([p, p])["statusCode"] == 400
    batch = [{**p, "id": f"app-{i}"} for i in range(10)]
    assert send(batch)["statusCode"] == 200
    assert len(store.list_systems()) == 10
    assert send([p])["statusCode"] == 409
    batch[0]["name"] = "Updated app"
    assert send([batch[0]])["statusCode"] == 200
    assert store.get_system("app-0").name == "Updated app"


def test_invalid_evidence_is_a_quality_notice_not_an_action_item(
    store, passport, snapshot, monkeypatch
):
    from conftest import make_finding

    monkeypatch.setenv("BW_OWNER_TOKEN", "owner-test-key")
    store.upsert_system(passport)
    finding = make_finding(passport, snapshot)
    finding.unknowns = ["snap_0adee73e7511; quoted passage not found verbatim in snapshot"]
    store.save_finding(finding)
    result = dispatch(event("/api/workspace"), store, Settings(), None)
    payload = json.loads(result["body"])
    assert not payload["findings"]
    assert payload["quality"][0]["system_id"] == passport.id
    assert "snap_0adee73e7511" not in result["body"]
