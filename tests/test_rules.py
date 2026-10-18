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
    findings, problems = assess(passport, {snapshot.id: snapshot}, {source.id: source}, "run-free")
    finding = findings[0]
    assert not problems
    assert not finding.validate_grounding(passport)
    assert finding.evidence[0].passage in snapshot.content
    assert finding.assessment_method == "rules-v3"
    assert "impact has not been assessed" in finding.inferences[0]
    assert finding.adoption_status.value == "unknown"
    repeated, _ = assess(passport, {snapshot.id: snapshot}, {source.id: source}, "run-next")
    again = repeated[0]
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


def test_every_changed_development_is_returned(passport, snapshot, source):
    lines = [
        "Gmail API requires DKIM authentication for bulk senders.",
        "Gmail API is retiring the legacy mail sending endpoint.",
    ]
    snapshot.content = "\n".join(lines)
    snapshot.added_passages = lines
    findings, problems = assess(passport, {snapshot.id: snapshot}, {source.id: source}, "run-all")
    assert not problems
    assert isinstance(findings, list)
    assert {f.evidence[0].passage for f in findings} == set(lines)
    assert len({f.development_key for f in findings}) == len(lines)


def test_partial_product_names_do_not_create_security_matches(passport, snapshot, source):
    passport.services = ["Microsoft Graph API"]
    passport.technologies = []
    source = source.model_copy(update={"id": "cisa-kev", "category": SourceCategory.SECURITY})
    passage = "Graph visualization library requires a security update for its renderer."
    snapshot.content = passage
    snapshot.added_passages = [passage]
    assert screen(passport, snapshot, source).plausible == "no"


def test_known_product_alias_is_matched_without_partial_tokens(passport, snapshot, source):
    passport.services = ["Microsoft Graph API"]
    passport.technologies = []
    source = source.model_copy(update={"id": "cisa-kev", "category": SourceCategory.SECURITY})
    passage = "Microsoft Graph requires a security update for its authentication endpoint."
    snapshot.content = passage
    snapshot.added_passages = [passage]
    assert screen(passport, snapshot, source).plausible == "possible"


def test_pipeline_persists_all_changes_and_retries_interrupted_pair(
    tmp_path,
    store,
    passport,
    source,
    monkeypatch,
):
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"sources": [source.model_dump(mode="json")]}))
    replay = tmp_path / "replay"
    replay.mkdir()
    capture = replay / (source.id + ".yaml")
    capture.write_text(yaml.safe_dump({"content": "An established sender baseline."}))
    settings = Settings(registry_path=registry, replay_dir=replay)
    store.upsert_system(passport)
    baseline = run_scan(store, settings)
    assert baseline.run.baseline_sources == [source.id]
    lines = [
        "Gmail requires DKIM authentication for bulk senders.",
        "Gmail is retiring the legacy mail sending endpoint.",
    ]
    capture.write_text(
        yaml.safe_dump({"content": "An established sender baseline.\n" + "\n".join(lines)})
    )
    original = store.save_finding
    calls = []

    def interrupt_second(finding):
        calls.append(finding)
        if len(calls) == 2:
            raise RuntimeError("Simulated persistence interruption")
        return original(finding)

    with monkeypatch.context() as patch:
        patch.setattr(store, "save_finding", interrupt_second)
        assert run_scan(store, settings).run.status == "aborted"
    retry = run_scan(store, settings)
    assert retry.run.status == "complete"
    assert len(retry.suppressed_duplicates) == 1
    assert len(retry.new_findings) == 1
    assert len(store.list_findings()) == 2
    assert not run_scan(store, settings).new_findings
    assert retry.run.model_id is None
    assert retry.run.estimated_cost_usd == 0


@pytest.mark.parametrize("filtered_retry", [False, True])
def test_interrupted_changes_survive_later_page_edits(
    tmp_path, store, passport, source, monkeypatch, filtered_retry
):
    from builtwatch import pipeline

    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"sources": [source.model_dump(mode="json")]}))
    replay = tmp_path / "replay"
    replay.mkdir()
    capture = replay / (source.id + ".yaml")
    baseline = "An established sender baseline."
    requirement = "Gmail requires DKIM authentication for bulk senders."
    settings = Settings(registry_path=registry, replay_dir=replay)
    store.upsert_system(passport)
    other = passport.model_copy(update={"id": "second-app"}, deep=True)
    store.upsert_system(other)
    capture.write_text(yaml.safe_dump({"content": baseline}))
    run_scan(store, settings)
    capture.write_text(yaml.safe_dump({"content": baseline + "\n" + requirement}))
    with monkeypatch.context() as patch:
        def interrupt(*args, **kwargs):
            raise RuntimeError("Simulated assessment interruption")
        patch.setattr(pipeline, "screen", interrupt)
        assert run_scan(store, settings).run.status == "aborted"
    capture.write_text(yaml.safe_dump({"content": baseline + "\n" + requirement + "\nContact us."}))
    retry = run_scan(store, settings, system_ids=[passport.id] if filtered_retry else None)
    assert retry.run.status == "complete"
    assert len(retry.new_findings) == (1 if filtered_retry else 2)
    if filtered_retry:
        # Another edit and a scoped scan must not consume a different app's pending work.
        capture.write_text(
            yaml.safe_dump({"content": baseline + "\n" + requirement + "\nContact us.\nHelp."})
        )
        run_scan(store, settings, system_ids=[passport.id])
        assert len(run_scan(store, settings, system_ids=[other.id]).new_findings) == 1
    capture.write_text(
        yaml.safe_dump({"content": baseline + "\n" + requirement + "\nUpdated contact."})
    )
    completed = run_scan(store, settings)
    assert not completed.new_findings
    assert not completed.suppressed_duplicates  # Completed deltas do not accumulate forever.
    assert completed.run.estimated_cost_usd == 0


def test_linked_security_product_matches_with_exact_grounding(passport, snapshot, source):
    from builtwatch.fetch import extract_text

    passport.services = ["OpenSSL"]
    source = source.model_copy(update={"category": SourceCategory.SECURITY})
    snapshot.content = extract_text(
        '<p>A security vulnerability requires an urgent update to '
        '<a href="/openssl"><strong>OpenSSL</strong></a>.</p>', 1000
    )
    snapshot.added_passages = snapshot.content.splitlines()
    assert screen(passport, snapshot, source).plausible == "possible"
    findings, problems = assess(passport, {snapshot.id: snapshot}, {source.id: source}, "linked")
    assert not problems
    assert len(findings) == 1
    assert not findings[0].validate_grounding(passport)
    assert findings[0].evidence[0].passage in snapshot.content
    snapshot.content = extract_text(
        '<p>A security vulnerability requires an urgent update to Windows.</p>'
        '<p><a href="/openssl">OpenSSL</a> documentation and examples.</p>', 1000
    )
    snapshot.added_passages = snapshot.content.splitlines()
    assert screen(passport, snapshot, source).plausible == "no"


@pytest.mark.parametrize("cosmetic", [str.upper, lambda text: text.replace(" ", "  ")])
def test_cosmetic_edit_rebinds_interrupted_evidence(
    tmp_path, store, passport, source, monkeypatch, cosmetic
):
    from builtwatch import pipeline

    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"sources": [source.model_dump(mode="json")]}))
    replay = tmp_path / "replay"
    replay.mkdir()
    capture = replay / (source.id + ".yaml")
    baseline = "An established sender baseline."
    passage = "Gmail requires DKIM authentication for bulk senders."
    settings = Settings(registry_path=registry, replay_dir=replay)
    store.upsert_system(passport)
    capture.write_text(yaml.safe_dump({"content": baseline}))
    run_scan(store, settings)
    capture.write_text(yaml.safe_dump({"content": baseline + "\n" + passage}))
    with monkeypatch.context() as patch:
        def interrupt(*args, **kwargs):
            raise RuntimeError("Simulated assessment interruption")
        patch.setattr(pipeline, "screen", interrupt)
        assert run_scan(store, settings).run.status == "aborted"
    capture.write_text(yaml.safe_dump({"content": cosmetic(baseline + "\n" + passage)}))
    retry = run_scan(store, settings)
    assert len(retry.new_findings) == 1
    assert retry.new_findings[0].evidence[0].passage == cosmetic(passage)
    assert not retry.new_findings[0].validate_grounding(passport)
    assert not run_scan(store, settings).new_findings


def test_extractor_upgrade_does_not_manufacture_an_external_change(
    tmp_path, store, passport, source
):
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"sources": [source.model_dump(mode="json")]}))
    replay = tmp_path / "replay"
    replay.mkdir()
    capture = replay / (source.id + ".yaml")
    old = "Gmail requires DKIM authentication for\nbulk senders\n."
    new = "Gmail requires DKIM authentication for bulk senders."
    settings = Settings(registry_path=registry, replay_dir=replay)
    store.upsert_system(passport)
    capture.write_text(yaml.safe_dump({"content": old}))
    run_scan(store, settings)
    capture.write_text(yaml.safe_dump({"content": new}))
    assert not run_scan(store, settings).new_findings
    actual = "Gmail is retiring its legacy message endpoint."
    capture.write_text(yaml.safe_dump({"content": new + "\n" + actual}))
    assert run_scan(store, settings).new_findings[0].evidence[0].passage == actual


def test_long_passages_and_multiple_dependencies_remain_grounded(passport, snapshot, source):
    passport.services = ["Gmail API", "SendGrid"]
    passage = "Gmail and SendGrid require a security update for bulk senders."
    snapshot.content = "Background information. " * 80 + passage
    snapshot.added_passages = [snapshot.content]
    findings, problems = assess(passport, {snapshot.id: snapshot}, {source.id: source}, "run-long")
    assert findings and not problems
    assert any(passage in e.passage for f in findings for e in f.evidence)
    for finding in findings:
        assert len(finding.evidence[0].passage) <= 1200
        assert not finding.validate_grounding(passport)
    assert any({ref.value for ref in f.system_facts} == set(passport.services) for f in findings)


def test_engine_upgrade_preserves_legacy_identity_and_outcome(
    tmp_path,
    store,
    passport,
    snapshot,
    source,
):
    import hashlib

    from builtwatch.models import Disposition, DispositionAction
    from builtwatch.quality import QUALITY_VERSION

    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump({"sources": [source.model_dump(mode="json")]}))
    replay = tmp_path / "replay"
    replay.mkdir()
    capture = replay / (source.id + ".yaml")
    capture.write_text(yaml.safe_dump({"content": "Sender baseline only."}))
    settings = Settings(registry_path=registry, replay_dir=replay)
    store.upsert_system(passport)
    run_scan(store, settings)
    passage = "Gmail requires DKIM authentication for bulk senders."
    snapshot.content = passage
    snapshot.added_passages = [passage]
    candidates, _ = assess(passport, {snapshot.id: snapshot}, {source.id: source}, "legacy-run")
    old = candidates[0]
    old.development_key = f"rules:{source.id}:" + hashlib.sha256(passage.encode()).hexdigest()[:20]
    old.assessment_method = "rules-v1"
    old.quality_version = QUALITY_VERSION
    store.save_finding(old)
    store.add_disposition(
        Disposition(id="disp_legacy", finding_id=old.id, action=DispositionAction.ACKNOWLEDGED)
    )
    capture.write_text(yaml.safe_dump({"content": "Sender baseline only.\n" + passage.upper()}))
    upgraded = run_scan(store, settings)
    assert upgraded.run.status == "complete"
    assert not upgraded.new_findings
    assert len(upgraded.suppressed_duplicates) == 1
    assert len(store.list_findings()) == 1
    assert store.dispositions_for(old.id)[0].action is DispositionAction.ACKNOWLEDGED
