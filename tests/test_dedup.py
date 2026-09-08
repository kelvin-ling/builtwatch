"""Repeated scans must stay quiet; changed substance must speak up."""

from __future__ import annotations

from conftest import make_finding

from builtwatch.models import Disposition, DispositionAction, Relevance
from builtwatch.store import new_id


def test_identical_finding_is_not_stored_twice(store, passport, snapshot):
    store.upsert_system(passport)
    first, is_new_1 = store.save_finding(make_finding(passport, snapshot, finding_id="find_a"))
    second, is_new_2 = store.save_finding(make_finding(passport, snapshot, finding_id="find_b"))

    assert is_new_1 is True
    assert is_new_2 is False, "a re-scan over unchanged material must not create a new finding"
    assert second.id == first.id
    assert len(store.list_findings()) == 1


def test_material_change_creates_a_new_revision(store, passport, snapshot):
    store.upsert_system(passport)
    store.save_finding(make_finding(passport, snapshot, finding_id="find_a"))

    changed = make_finding(
        passport,
        snapshot,
        finding_id="find_b",
        facts=["The requirement now also applies to transactional mail."],
    )
    _, is_new = store.save_finding(changed)

    assert is_new is True, "changed substance must produce a new finding"
    current = store.list_findings(current_only=True)
    assert len(current) == 1, "only the newest revision is current"
    assert current[0].id == "find_b"
    assert len(store.list_findings(current_only=False)) == 2, "history is preserved"


def test_cosmetic_change_does_not_create_a_revision(store, passport, snapshot):
    """Whitespace and casing churn in a source must not look like news."""
    store.upsert_system(passport)
    original = make_finding(passport, snapshot, finding_id="find_a")
    store.save_finding(original)

    noisy = make_finding(passport, snapshot, finding_id="find_b")
    noisy.evidence[0].passage = "  " + noisy.evidence[0].passage.upper().replace(" ", "  ") + " "

    _, is_new = store.save_finding(noisy)
    assert is_new is False


def test_disposed_development_stays_down(store, passport, snapshot):
    store.upsert_system(passport)
    finding, _ = store.save_finding(make_finding(passport, snapshot))
    store.add_disposition(
        Disposition(
            id=new_id("disp"),
            finding_id=finding.id,
            action=DispositionAction.DISMISSED,
            reason="We migrated off Gmail in March.",
        )
    )
    assert store.is_disposed(finding.dedup_key()) is True


def test_export_disposition_does_not_suppress(store, passport, snapshot):
    """Exporting a finding is not the same as deciding about it."""
    store.upsert_system(passport)
    finding, _ = store.save_finding(make_finding(passport, snapshot))
    store.add_disposition(
        Disposition(
            id=new_id("disp"), finding_id=finding.id, action=DispositionAction.EXPORTED
        )
    )
    assert store.is_disposed(finding.dedup_key()) is False


def test_findings_survive_restart(tmp_path, passport, snapshot):
    from builtwatch.store import Store

    db = tmp_path / "persist.db"
    s1 = Store(db)
    s1.upsert_system(passport)
    finding, _ = s1.save_finding(make_finding(passport, snapshot))
    s1.add_disposition(
        Disposition(
            id=new_id("disp"), finding_id=finding.id, action=DispositionAction.ACKNOWLEDGED
        )
    )
    s1.close()

    s2 = Store(db)
    reloaded = s2.get_finding(finding.id)
    assert reloaded is not None
    assert reloaded.relevance is Relevance.RELEVANT
    assert [d.action for d in s2.dispositions_for(finding.id)] == [
        DispositionAction.ACKNOWLEDGED
    ]
    s2.close()


def test_cost_ledger_accumulates(store):
    store.record_cost("run_1", "model-x", 1000, 500, 0.01)
    store.record_cost("run_2", "model-x", 2000, 800, 0.02)
    assert abs(store.spent_today() - 0.03) < 1e-9
    assert abs(store.spent_this_month() - 0.03) < 1e-9
