"""End-to-end pipeline behaviour, with the model stubbed out. No AWS calls."""

from __future__ import annotations

import yaml
from conftest import SNAPSHOT_TEXT, make_finding

from builtwatch import pipeline
from builtwatch.agent.relevance import ScreenVerdict
from builtwatch.config import BudgetExceeded, Settings
from builtwatch.models import FetchStatus, Relevance


def _settings(tmp_path, registry_body: dict, replay: dict[str, dict | None]) -> Settings:
    registry = tmp_path / "registry.yaml"
    registry.write_text(yaml.safe_dump(registry_body), encoding="utf-8")
    replay_dir = tmp_path / "replay"
    replay_dir.mkdir()
    for source_id, payload in replay.items():
        if payload is not None:
            (replay_dir / f"{source_id}.yaml").write_text(
                yaml.safe_dump(payload), encoding="utf-8"
            )
    settings = Settings()
    settings.registry_path = registry
    settings.replay_dir = replay_dir
    settings.db_path = tmp_path / "pipeline.db"
    return settings


GMAIL_SOURCE = {
    "id": "gmail-sender-guidelines",
    "name": "Gmail Email Sender Guidelines",
    "category": "communications",
    "url": "https://support.google.com/mail/answer/81126",
    "publisher": "Google",
}
BROKEN_SOURCE = {
    "id": "never-captured",
    "name": "A Source With No Snapshot",
    "category": "regulation",
    "url": "https://example.org/regulation",
    "publisher": "Nobody",
}


def test_failed_source_is_a_loud_coverage_failure(tmp_path, store, passport, monkeypatch):
    """The headline property: a fetch failure can never look like a quiet, clean scan."""
    settings = _settings(
        tmp_path,
        {"sources": [GMAIL_SOURCE, BROKEN_SOURCE]},
        {"gmail-sender-guidelines": {"content": SNAPSHOT_TEXT}, "never-captured": None},
    )
    store.upsert_system(passport)
    monkeypatch.setattr(
        pipeline, "screen", lambda *a, **k: ScreenVerdict(plausible="no", reason="unrelated")
    )

    result = pipeline.run_scan(store, settings, mode="replay")

    assert len(result.coverage_failures) == 1
    failure = result.coverage_failures[0]
    assert failure.source_id == "never-captured"
    assert failure.fetch_status is FetchStatus.SKIPPED
    assert "COULD NOT BE CHECKED" in result.summary_line()
    assert result.run.coverage_complete is False


def test_clean_scan_reports_complete_coverage(tmp_path, store, passport, monkeypatch):
    settings = _settings(
        tmp_path,
        {"sources": [GMAIL_SOURCE]},
        {"gmail-sender-guidelines": {"content": SNAPSHOT_TEXT}},
    )
    store.upsert_system(passport)
    monkeypatch.setattr(
        pipeline, "screen", lambda *a, **k: ScreenVerdict(plausible="no", reason="unrelated")
    )

    result = pipeline.run_scan(store, settings, mode="replay")

    assert result.coverage_failures == []
    assert result.run.coverage_complete is True
    assert result.screened_out == 1
    assert "COULD NOT BE CHECKED" not in result.summary_line()


def test_screening_prevents_expensive_assessment(tmp_path, store, passport, monkeypatch):
    """A 'no' at the screen stage must never reach the expensive model."""
    settings = _settings(
        tmp_path,
        {"sources": [GMAIL_SOURCE]},
        {"gmail-sender-guidelines": {"content": SNAPSHOT_TEXT}},
    )
    store.upsert_system(passport)
    called = []
    monkeypatch.setattr(
        pipeline, "screen", lambda *a, **k: ScreenVerdict(plausible="no", reason="unrelated")
    )
    monkeypatch.setattr(pipeline, "assess", lambda *a, **k: called.append(1) or (None, []))

    pipeline.run_scan(store, settings, mode="replay")
    assert called == [], "assessment ran despite the screen saying no"


def test_rewritten_source_does_not_re_notify_the_same_development(
    tmp_path, store, passport, monkeypatch
):
    """The dedup layer, exercised properly.

    A source page gets edited — a nav tweak, a new date stamp — so its content hash
    changes and the pair is assessed again. The underlying development is identical, so
    the finding must be recognised as already reported and stay silent.
    """
    settings = _settings(
        tmp_path,
        {"sources": [GMAIL_SOURCE]},
        {"gmail-sender-guidelines": {"content": SNAPSHOT_TEXT}},
    )
    store.upsert_system(passport)
    monkeypatch.setattr(
        pipeline, "screen", lambda *a, **k: ScreenVerdict(plausible="yes", reason="mentions email")
    )

    def fake_assess(passport, snapshots, sources, scan_run_id, settings, meter):
        snap = next(iter(snapshots.values()))
        finding = make_finding(passport, snap, passage=SNAPSHOT_TEXT[:120])
        finding.scan_run_id = scan_run_id
        finding.source_id = snap.source_id
        finding.evidence[0].snapshot_id = snap.id
        finding.evidence[0].source_id = snap.source_id
        return finding, []

    monkeypatch.setattr(pipeline, "assess", fake_assess)

    first = pipeline.run_scan(store, settings, mode="replay")
    assert len(first.new_findings) == 1
    assert first.new_findings[0].relevance is Relevance.RELEVANT

    # The page is edited around the substance. Hash changes; the news does not.
    (settings.replay_dir / "gmail-sender-guidelines.yaml").write_text(
        yaml.safe_dump(
            {"content": SNAPSHOT_TEXT + "\n\nPage last reviewed 8 September 2026."}
        ),
        encoding="utf-8",
    )

    second = pipeline.run_scan(store, settings, mode="replay")
    assert second.new_findings == [], "a rewritten page re-notified an unchanged development"
    assert len(second.suppressed_duplicates) == 1
    assert len(store.list_findings(current_only=True)) == 1


def test_acknowledged_finding_is_not_raised_again(tmp_path, store, passport, monkeypatch):
    """Once a person has decided about a development, it stays down."""
    from builtwatch.models import Disposition, DispositionAction
    from builtwatch.store import new_id

    settings = _settings(
        tmp_path,
        {"sources": [GMAIL_SOURCE]},
        {"gmail-sender-guidelines": {"content": SNAPSHOT_TEXT}},
    )
    store.upsert_system(passport)
    monkeypatch.setattr(
        pipeline, "screen", lambda *a, **k: ScreenVerdict(plausible="yes", reason="email")
    )

    def fake_assess(passport, snapshots, sources, scan_run_id, settings, meter):
        snap = next(iter(snapshots.values()))
        finding = make_finding(passport, snap, passage=SNAPSHOT_TEXT[:120])
        finding.scan_run_id = scan_run_id
        finding.source_id = snap.source_id
        finding.evidence[0].snapshot_id = snap.id
        finding.evidence[0].source_id = snap.source_id
        return finding, []

    monkeypatch.setattr(pipeline, "assess", fake_assess)

    first = pipeline.run_scan(store, settings, mode="replay")
    store.add_disposition(
        Disposition(
            id=new_id("disp"),
            finding_id=first.new_findings[0].id,
            action=DispositionAction.ACKNOWLEDGED,
        )
    )

    (settings.replay_dir / "gmail-sender-guidelines.yaml").write_text(
        yaml.safe_dump({"content": SNAPSHOT_TEXT + "\n\nMinor editorial revision."}),
        encoding="utf-8",
    )
    second = pipeline.run_scan(store, settings, mode="replay")
    assert second.new_findings == []
    assert len(second.suppressed_duplicates) == 1


def test_unchanged_source_is_not_reassessed(tmp_path, store, passport, monkeypatch):
    """Second run: the content hash is unchanged, so the model is never invoked at all."""
    settings = _settings(
        tmp_path,
        {"sources": [GMAIL_SOURCE]},
        {"gmail-sender-guidelines": {"content": SNAPSHOT_TEXT}},
    )
    store.upsert_system(passport)
    screens = []
    monkeypatch.setattr(
        pipeline,
        "screen",
        lambda *a, **k: screens.append(1)
        or ScreenVerdict(plausible="no", reason="unrelated"),
    )

    pipeline.run_scan(store, settings, mode="replay")
    assert len(screens) == 1
    pipeline.run_scan(store, settings, mode="replay")
    assert len(screens) == 1, "an unchanged source was re-screened, wasting money"


def test_budget_abort_marks_run_aborted_not_clean(tmp_path, store, passport, monkeypatch):
    """Hitting a ceiling aborts loudly. It must never resemble a completed quiet scan."""
    settings = _settings(
        tmp_path,
        {"sources": [GMAIL_SOURCE]},
        {"gmail-sender-guidelines": {"content": SNAPSHOT_TEXT}},
    )
    store.upsert_system(passport)

    def boom(*a, **k):
        raise BudgetExceeded("daily ceiling reached")

    monkeypatch.setattr(pipeline, "screen", boom)

    result = pipeline.run_scan(store, settings, mode="replay")
    assert result.run.status == "aborted"
    assert "daily ceiling" in result.run.abort_reason
    assert "aborted" in result.summary_line().lower()


def test_unexpected_error_marks_run_aborted(tmp_path, store, passport, monkeypatch):
    """A crash must leave the run visibly aborted, never stuck at 'running'.

    A run left in 'running' is indistinguishable from one still in flight — the exact
    ambiguity BuiltWatch exists to eliminate.
    """
    settings = _settings(
        tmp_path,
        {"sources": [GMAIL_SOURCE]},
        {"gmail-sender-guidelines": {"content": SNAPSHOT_TEXT}},
    )
    store.upsert_system(passport)

    def boom(*a, **k):
        raise RuntimeError("Bedrock said no")

    monkeypatch.setattr(pipeline, "screen", boom)

    result = pipeline.run_scan(store, settings, mode="replay")

    assert result.run.status == "aborted"
    assert "RuntimeError" in result.run.abort_reason
    assert "Bedrock said no" in result.run.abort_reason
    assert result.run.finished_at is not None

    # And it is persisted that way, so `builtwatch status` cannot show a phantom run.
    reloaded = store.get_run(result.run.id)
    assert reloaded.status == "aborted"
