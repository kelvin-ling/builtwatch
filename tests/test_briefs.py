"""AI impact briefs are grounded, capped, optional and never fail a scan."""

from __future__ import annotations

import json

import pytest
from conftest import SNAPSHOT_TEXT, make_finding

from builtwatch.briefs import attach_briefs, validate
from builtwatch.config import Settings
from builtwatch.models import SystemPassport


class FakeBedrock:
    def __init__(self, payload, error=None):
        self.payload, self.error, self.calls = payload, error, 0

    def converse(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        if self.error:
            raise self.error
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return {
            "output": {"message": {"content": [{"text": f"```json\n{text}\n```"}]}},
            "usage": {"inputTokens": 1500, "outputTokens": 200},
        }


GOOD = {
    "verdict": "likely_affects",
    "component_id": "outbound",
    "what_changes": "Bulk senders must authenticate mail with SPF, DKIM and DMARC.",
    "why_it_matters": "The bot sends client email through SendGrid from the business domain.",
    "check_first": "Confirm SPF, DKIM and DMARC are set for the sending domain.",
    "support_quote": "bulk senders must authenticate outgoing mail with SPF and DKIM",
}


@pytest.fixture
def mapped(passport) -> SystemPassport:
    data = passport.model_dump(mode="json")
    data["architecture"] = {
        "components": [
            {"id": "outbound", "name": "Outbound email", "kind": "external", "uses": ["SendGrid"]}
        ]
    }
    return SystemPassport.model_validate(data)


def _settings(monkeypatch, **env) -> Settings:
    monkeypatch.setenv("BW_AI_BRIEFS", "on")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings()


def _stored(store, mapped, snapshot):
    store.upsert_system(mapped)
    finding = make_finding(mapped, snapshot, passage=SNAPSHOT_TEXT)
    finding.assessment_method = "rules-v3.1"
    stored, _ = store.save_finding(finding)
    return stored


def test_grounded_brief_is_attached_with_its_cost(store, mapped, snapshot, monkeypatch):
    finding = _stored(store, mapped, snapshot)
    client = FakeBedrock(GOOD)
    stats = attach_briefs(store, _settings(monkeypatch), [finding], client=client)
    assert stats["briefed"] == 1
    brief = store.get_finding(finding.id).ai_brief
    assert brief.verdict == "likely_affects" and brief.component_id == "outbound"
    assert brief.cost_usd > 0 and brief.model_id == "us.amazon.nova-lite-v1:0"
    # The source text is delimited as data, and the model gets no tools.
    prompt = client.kwargs["messages"][0]["content"][0]["text"]
    assert "<passage>" in prompt and "toolConfig" not in client.kwargs


@pytest.mark.parametrize(
    "change",
    [
        {"support_quote": "senders must send a fax to Google"},
        {"component_id": "invented"},
        {"verdict": "definitely"},
    ],
)
def test_ungrounded_brief_is_discarded_and_the_review_stands(
    store, mapped, snapshot, monkeypatch, change
):
    finding = _stored(store, mapped, snapshot)
    stats = attach_briefs(
        store, _settings(monkeypatch), [finding], client=FakeBedrock({**GOOD, **change})
    )
    assert stats["discarded"] == 1
    kept = store.get_finding(finding.id)
    assert kept.ai_brief is None and kept.relevance == finding.relevance


def test_monthly_count_cap_stops_calls(store, mapped, snapshot, monkeypatch):
    finding = _stored(store, mapped, snapshot)
    other = make_finding(mapped, snapshot, passage=SNAPSHOT_TEXT, finding_id="find_two")
    other.assessment_method, other.development_key = "rules-v3.1", "other-key"
    other, _ = store.save_finding(other)
    client = FakeBedrock(GOOD)
    settings = _settings(monkeypatch, BW_AI_BRIEF_MONTH_COUNT="1")
    stats = attach_briefs(store, settings, [finding, other], client=client)
    assert client.calls == 1 and stats["briefed"] == 1 and stats["skipped"] >= 1


def test_usd_cap_stops_calls_before_spending(store, mapped, snapshot, monkeypatch):
    finding = _stored(store, mapped, snapshot)
    client = FakeBedrock(GOOD)
    attach_briefs(
        store, _settings(monkeypatch, BW_AI_BRIEF_MONTH_USD="0.0001"), [finding], client=client
    )
    assert client.calls == 0


def test_briefs_are_off_unless_switched_on(store, mapped, snapshot, monkeypatch):
    monkeypatch.delenv("BW_AI_BRIEFS", raising=False)
    finding = _stored(store, mapped, snapshot)
    client = FakeBedrock(GOOD)
    assert attach_briefs(store, Settings(), [finding], client=client)["skipped"] == 1
    assert client.calls == 0


def test_model_error_is_counted_not_raised(store, mapped, snapshot, monkeypatch):
    finding = _stored(store, mapped, snapshot)
    client = FakeBedrock(GOOD, error=RuntimeError("throttled"))
    stats = attach_briefs(store, _settings(monkeypatch), [finding], client=client)
    assert stats["errors"] == 1 and store.get_finding(finding.id).ai_brief is None


def test_brief_does_not_change_the_revision_hash(mapped, snapshot):
    finding = make_finding(mapped, snapshot, passage=SNAPSHOT_TEXT)
    before = finding.compute_revision_hash()
    assert not validate(GOOD, mapped, finding)
    from builtwatch.models import AIBrief

    finding.ai_brief = AIBrief(model_id="m", **GOOD)
    assert finding.compute_revision_hash() == before


def test_owner_pause_stops_briefs(store, mapped, snapshot, monkeypatch):
    if not hasattr(store, "table"):
        pytest.skip("the manual pause lives in the shared DynamoDB table")
    store.table.put_item(Item={"pk": "ADMIN", "sk": "control", "paused": True})
    finding = _stored(store, mapped, snapshot)
    client = FakeBedrock(GOOD)
    attach_briefs(store, _settings(monkeypatch), [finding], client=client)
    assert client.calls == 0
