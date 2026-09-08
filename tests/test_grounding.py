"""A relevance claim must be grounded in real evidence and a real passport fact."""

from __future__ import annotations

from conftest import SNAPSHOT_TEXT, make_finding

from builtwatch.models import Relevance


def test_grounded_finding_passes(passport, snapshot):
    finding = make_finding(passport, snapshot)
    assert finding.validate_grounding(passport) == []


def test_invented_fact_key_is_rejected(passport, snapshot):
    """The model cannot cite a passport field that does not exist."""
    finding = make_finding(passport, snapshot, fact_key="services[47]", fact_value="Gmail API")
    problems = finding.validate_grounding(passport)
    assert any("does not exist" in p for p in problems)


def test_mismatched_fact_value_is_rejected(passport, snapshot):
    """Citing a real key with a value the passport never stated is caught."""
    finding = make_finding(passport, snapshot, fact_key="services[0]", fact_value="Mailchimp")
    problems = finding.validate_grounding(passport)
    assert any("does not match passport" in p for p in problems)


def test_relevant_without_evidence_is_rejected(passport, snapshot):
    finding = make_finding(passport, snapshot)
    finding.evidence = []
    problems = finding.validate_grounding(passport)
    assert any("no evidence passage" in p for p in problems)


def test_relevant_without_system_fact_is_rejected(passport, snapshot):
    finding = make_finding(passport, snapshot)
    finding.system_facts = []
    problems = finding.validate_grounding(passport)
    assert any("cites no system fact" in p for p in problems)


def test_insufficient_information_needs_no_evidence(passport, snapshot):
    """'I cannot tell' is a legitimate answer and is not forced to cite anything."""
    finding = make_finding(passport, snapshot, relevance=Relevance.INSUFFICIENT_INFORMATION)
    finding.evidence = []
    finding.system_facts = []
    assert finding.validate_grounding(passport) == []


def test_fabricated_quote_is_caught_by_pipeline_conversion(passport, snapshot):
    """A passage that is not verbatim in the snapshot never becomes evidence."""
    from builtwatch.agent.relevance import DraftEvidence, DraftSystemFact, FindingDraft, _to_finding
    from builtwatch.agent.tools import InvestigationContext

    draft = FindingDraft(
        relevance="relevant",
        title="Invented claim",
        development_key="made-up",
        evidence=[
            DraftEvidence(
                snapshot_id=snapshot.id,
                passage="Senders must now pay a licensing fee of $500 per month to Google.",
            )
        ],
        system_facts=[DraftSystemFact(key="services[0]", value="Gmail API")],
    )
    ctx = InvestigationContext(passport=passport, snapshots={}, sources={})
    finding, problems = _to_finding(draft, passport, {snapshot.id: snapshot}, "run_x", ctx)

    assert any("not found verbatim" in p for p in problems)
    # An ungrounded "relevant" claim is downgraded rather than published as fact.
    assert finding.relevance is Relevance.INSUFFICIENT_INFORMATION
    assert any("Downgraded automatically" in u for u in finding.unknowns)


def test_real_quote_survives_conversion(passport, snapshot):
    from builtwatch.agent.relevance import DraftEvidence, DraftSystemFact, FindingDraft, _to_finding
    from builtwatch.agent.tools import InvestigationContext

    draft = FindingDraft(
        relevance="relevant",
        title="Gmail bulk sender requirements",
        development_key="gmail-bulk-sender-2026",
        adoption_status="adopted",
        evidence=[DraftEvidence(snapshot_id=snapshot.id, passage=SNAPSHOT_TEXT[:120])],
        system_facts=[DraftSystemFact(key="services[0]", value="Gmail API")],
    )
    ctx = InvestigationContext(passport=passport, snapshots={}, sources={})
    finding, problems = _to_finding(draft, passport, {snapshot.id: snapshot}, "run_x", ctx)

    assert problems == []
    assert finding.relevance is Relevance.RELEVANT
    assert finding.evidence[0].passage == SNAPSHOT_TEXT[:120]
