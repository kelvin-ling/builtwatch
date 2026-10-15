"""The default monitoring path must never instantiate a paid model."""

from __future__ import annotations

import json

import pytest
import yaml

from builtwatch.agent import relevance
from builtwatch.config import CostMeter, Settings
from builtwatch.intake import from_text
from builtwatch.models import SourceCategory
from builtwatch.pipeline import run_scan
from builtwatch.rules import assess, screen


def test_rules_default_and_paid_factory_fails_closed(monkeypatch):
    monkeypatch.delenv("BW_INFERENCE_MODE", raising=False)
    settings = Settings()
    assert settings.inference_mode == "rules"
    with pytest.raises(RuntimeError, match="Paid inference is disabled"):
        relevance._bedrock(settings, settings.assess_model_id)
    monkeypatch.setenv("BW_INFERENCE_MODE", "typo")
    with pytest.raises(ValueError, match="BW_INFERENCE_MODE"):
        Settings()


def test_only_added_material_passages_create_grounded_candidates(passport, snapshot, source):
    assert screen(passport, snapshot, source).plausible == "no"  # Baseline, not new news.
    passage = "Gmail API requires bulk senders to authenticate outgoing mail with DKIM."
    snapshot.content += "\n" + passage
    snapshot.added_passages = [passage]
    assert screen(passport, snapshot, source).plausible == "possible"
    finding, problems = assess(passport, {snapshot.id: snapshot}, {source.id: source}, "run-free")
    assert not problems
    assert not finding.validate_grounding(passport)
    assert finding.evidence[0].passage in snapshot.content
    assert finding.assessment_method == "rules-v1"
    assert "impact has not been assessed" in finding.inferences[0]
    assert finding.adoption_status.value == "unknown"
    again, _ = assess(passport, {snapshot.id: snapshot}, {source.id: source}, "run-next")
    assert again.development_key == finding.development_key
    assert again.revision_hash == finding.revision_hash


def test_navigation_forged_evidence_and_unrelated_products_stay_quiet(passport, snapshot, source):
    for passage in [
        "Gmail navigation: home about contact and help",
        "Windows has a security vulnerability.",
    ]:
        snapshot.content = passage
        snapshot.added_passages = [passage]
        assert (
            screen(
                passport, snapshot, source.model_copy(update={"category": SourceCategory.SECURITY})
            ).plausible
            == "no"
        )
    snapshot.added_passages = ["Gmail requires DKIM authentication for outgoing messages."]
    assert screen(passport, snapshot, source).plausible == "no"


def test_real_pipeline_detects_changes_deduplicates_and_never_calls_ai(
    tmp_path,
    store,
    passport,
    source,
    monkeypatch,
):
    def forbidden(*args, **kwargs):
        raise AssertionError("A free scan attempted paid AI")

    monkeypatch.setattr(relevance, "Agent", forbidden)
    monkeypatch.setattr(relevance, "BedrockModel", forbidden)
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"sources": [source.model_dump(mode="json")]}))
    replay = tmp_path / "replay"
    replay.mkdir()
    capture = replay / (source.id + ".yaml")
    capture.write_text(yaml.safe_dump({"content": "Gmail sender guidelines establish a baseline."}))
    settings = Settings(registry_path=registry, replay_dir=replay)
    store.upsert_system(passport)
    baseline = run_scan(store, settings)
    assert baseline.run.status == "complete"
    assert not baseline.new_findings
    capture.write_text(
        yaml.safe_dump(
            {
                "content": "Gmail sender guidelines establish a baseline.\n"
                "Gmail requires bulk senders to use DKIM authentication."
            }
        )
    )
    changed = run_scan(store, settings)
    assert len(changed.new_findings) == 1
    assert changed.run.estimated_cost_usd == 0
    assert changed.run.model_id is None
    assert changed.run.assessment_method == "rules"
    assert not run_scan(store, settings).new_findings


def test_text_draft_is_local_and_preserves_unknowns(monkeypatch):
    from builtwatch import intake

    monkeypatch.setattr(intake, "Agent", lambda **kw: pytest.fail("Paid intake attempted"))
    settings = Settings()
    meter = CostMeter(settings)
    profile = from_text("Mail helper\nA Python app reads Gmail API messages.", settings, meter)
    assert "gmail" in profile.services
    assert "Python" in profile.technologies
    assert not profile.jurisdictions
    assert not profile.consequential_actions
    assert profile.unknowns
    assert meter.run_cost == 0


def test_existing_paid_allowance_does_not_block_rules_checks(store, passport):
    from builtwatch.web_api import dispatch

    store.upsert_system(passport)
    store.record_cost("old-paid-run", "legacy-model", 0, 0, 5)
    calls = []
    result = dispatch(
        {"requestContext": {"http": {"method": "POST"}}, "rawPath": "/api/scan", "body": "{}"},
        store,
        Settings(),
        lambda: calls.append(True),
        verified=True,
    )
    assert result["statusCode"] == 202, json.loads(result["body"])
    assert calls == [True]
