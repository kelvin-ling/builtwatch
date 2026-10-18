"""Backend maps travel with the profile, are grounded in it, and never widen what is fetched."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from builtwatch.config import Settings
from builtwatch.models import SystemPassport
from builtwatch.web_api import dispatch

ROOT = Path(__file__).resolve().parents[1]


def _event(path, method="GET", body=None):
    return {
        "rawPath": path,
        "headers": {"authorization": "Bearer owner-test-key"},
        "requestContext": {"http": {"method": method}},
        "body": json.dumps(body) if body is not None else None,
    }


def _mapped(passport: SystemPassport, **component) -> dict:
    data = passport.model_dump(mode="json")
    dep = (passport.services or passport.technologies)[0]
    data["architecture"] = {
        "analyzed_by": "Repo agent",
        "components": [
            {"id": "api", "name": "API", "kind": "service", "uses": [dep], **component},
            {"id": "ext", "name": dep, "kind": "external", "uses": [dep.upper()]},
        ],
        "flows": [{"source": "api", "target": "ext", "label": "requests"}],
    }
    return data


def test_map_round_trips_through_the_workspace(store, passport, monkeypatch):
    monkeypatch.setenv("BW_OWNER_TOKEN", "owner-test-key")
    settings = Settings()
    result = dispatch(_event("/api/systems", "POST", _mapped(passport)), store, settings, None)
    assert result["statusCode"] == 200
    saved = json.loads(dispatch(_event("/api/workspace"), store, settings, None)["body"])
    arch = saved["systems"][0]["architecture"]
    assert [c["id"] for c in arch["components"]] == ["api", "ext"]
    assert arch["flows"][0] == {"source": "api", "target": "ext", "label": "requests"}


def test_ungrounded_component_is_rejected_without_writing(store, passport, monkeypatch):
    monkeypatch.setenv("BW_OWNER_TOKEN", "owner-test-key")
    data = _mapped(passport, uses=["A dependency the profile never records"])
    result = dispatch(_event("/api/systems", "POST", data), store, Settings(), None)
    assert result["statusCode"] == 400
    assert not store.list_systems()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda a: a["flows"].append({"source": "api", "target": "missing"}),
        lambda a: a["flows"].append({"source": "api", "target": "api"}),
        lambda a: a["components"].append(dict(a["components"][0])),
        lambda a: a["components"][0].update(kind="robot"),
        lambda a: a["components"][0].update(id="Not A Slug"),
    ],
)
def test_inconsistent_maps_are_rejected(passport, mutate):
    data = _mapped(passport)
    mutate(data["architecture"])
    with pytest.raises(ValidationError):
        SystemPassport.model_validate(data)


def test_profiles_without_a_map_are_unchanged(passport):
    assert SystemPassport.model_validate(passport.model_dump(mode="json")).architecture is None


def test_map_adds_no_fact_keys_or_fetchable_urls(passport):
    """Matching still keys off recorded facts; a map cannot introduce something to fetch."""
    mapped = SystemPassport.model_validate(_mapped(passport))
    assert mapped.fact_index() == passport.fact_index()


def test_example_and_demo_maps_are_valid():
    for path in (ROOT / "examples/passports").glob("*.json"):
        SystemPassport.model_validate(json.loads(path.read_text()))
    demo = json.loads((ROOT / "web/demo.json").read_text())
    mapped = [s for s in demo["systems"] if s.get("architecture")]
    assert {s["id"] for s in mapped} == {"support-widget", "inbox-triage"}
    for system in mapped:
        SystemPassport.model_validate(system)
