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
