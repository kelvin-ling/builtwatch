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
    assert any("could not verify the suggested connection" in u for u in finding.unknowns)


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
        facts=["Bulk senders must authenticate outgoing mail with SPF and DKIM."],
        app_impact={
            "fact_key": "services[0]",
            "consequence": "Gmail may reject this workflow's mail if sender rules are unmet.",
            "review_question": "Does this workflow meet the applicable sender rules?",
        },
    )
    ctx = InvestigationContext(passport=passport, snapshots={}, sources={})
    finding, problems = _to_finding(draft, passport, {snapshot.id: snapshot}, "run_x", ctx)

    assert problems == []
    assert finding.relevance is Relevance.RELEVANT
    assert finding.evidence[0].passage == SNAPSHOT_TEXT[:120]


def test_relevant_without_a_stated_fact_is_rejected(passport, snapshot):
    """Reasoning alone is not grounds to interrupt someone.

    Nova Pro reliably filled `inferences` while leaving `facts` empty, producing findings
    whose entire basis was the model's own reasoning. A relevance claim must rest on
    something the source actually states.
    """
    finding = make_finding(passport, snapshot)
    finding.facts = []
    problems = finding.validate_grounding(passport)
    assert any("states no fact from the source" in p for p in problems)


def test_facts_not_required_for_not_relevant(passport, snapshot):
    from builtwatch.models import Relevance

    finding = make_finding(passport, snapshot, relevance=Relevance.NOT_RELEVANT)
    finding.facts = []
    assert finding.validate_grounding(passport) == []


def test_passage_selection_copies_exact_source(passport, snapshot):
    from builtwatch.agent.relevance import DraftEvidence, DraftSystemFact, FindingDraft, _to_finding
    from builtwatch.agent.tools import InvestigationContext, passage_blocks

    ctx = InvestigationContext(passport=passport, snapshots={snapshot.id: snapshot}, sources={})
    passage_blocks(ctx, snapshot.id, snapshot.content)
    passage_id = next(iter(ctx.passages))
    draft = FindingDraft(
        relevance="relevant",
        title="Sender changes",
        development_key="sender-change",
        evidence=[DraftEvidence(passage_id=passage_id)],
        system_facts=[DraftSystemFact(key="services[0]", value="Gmail API")],
        facts=["Authentication is required."],
        app_impact={
            "fact_key": "services[0]",
            "consequence": "Gmail may reject this workflow's mail if sender rules are unmet.",
            "review_question": "Does this workflow meet the applicable sender rules?",
        },
    )
    finding, problems = _to_finding(draft, passport, ctx.snapshots, "run_x", ctx)
    assert not problems
    assert finding.evidence[0].passage == ctx.passages[passage_id][1]
    draft.evidence = [DraftEvidence(passage_id="p_invented")]
    finding, problems = _to_finding(draft, passport, ctx.snapshots, "run_x", ctx)
    assert problems and finding.validation_issues
    assert finding.relevance is Relevance.INSUFFICIENT_INFORMATION


def test_security_monitoring_does_not_imply_windows_dependency(passport):
    from builtwatch.quality import dependency_mismatch, source_out_of_scope

    passport.purpose = "Watch Windows vulnerabilities and security news for other apps"
    assert dependency_mismatch(passport, "Windows OS vulnerability")
    assert source_out_of_scope(passport, "stripe-upgrades")
    passport.technologies.append("Windows Server")
    assert not dependency_mismatch(passport, "Windows OS vulnerability")
    passport.services.append("Stripe API")
    assert not source_out_of_scope(passport, "stripe-upgrades")


def test_screening_receives_business_conditions_without_a_technology_stack(
    passport, snapshot, source, monkeypatch
):
    from types import SimpleNamespace

    from builtwatch.agent import relevance
    from builtwatch.config import CostMeter, Settings
    from builtwatch.models import ConsequentialAction

    passport.technologies = []
    passport.services = []
    passport.assumptions = ["Customer price lists are current"]
    passport.constraints = ["A person approves each quote"]
    passport.consequential_actions = [ConsequentialAction(description="Draft quotes for customers")]
    prompts = []

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        def __call__(self, prompt):
            prompts.append(prompt)
            return SimpleNamespace(
                structured_output=relevance.ScreenVerdict(
                    plausible="possible", reason="Recorded pricing assumption may be affected"
                )
            )

    monkeypatch.setattr(relevance, "Agent", FakeAgent)
    monkeypatch.setattr(relevance, "_bedrock", lambda *args: None)
    monkeypatch.setattr(relevance.BudgetGuard, "reconcile", lambda *args: None)
    settings = Settings()
    verdict = relevance.screen(passport, snapshot, source, settings, CostMeter(settings))
    assert verdict.plausible == "possible"
    for fact in [*passport.assumptions, *passport.constraints, "Draft quotes for customers"]:
        assert fact in prompts[0]


def test_impact_must_reference_a_cited_app_fact(passport, snapshot):
    from builtwatch.models import AppImpact

    finding = make_finding(passport, snapshot)
    finding.app_impact = AppImpact(
        fact_key="assumptions[99]",
        consequence="This workflow may send messages to the wrong audience.",
        review_question="Is the audience correctly recorded?",
    )
    assert "app impact is not anchored to a cited system fact" in finding.validate_grounding(
        passport
    )


def test_new_relevant_assessment_without_app_impact_is_withheld(passport, snapshot):
    from builtwatch.agent.relevance import FindingDraft, _to_finding
    from builtwatch.agent.tools import InvestigationContext

    draft = FindingDraft(
        relevance="relevant",
        title="Sender requirements",
        development_key="sender-rules",
        evidence=[{"snapshot_id": snapshot.id, "passage": SNAPSHOT_TEXT}],
        system_facts=[{"key": "services[0]", "value": "Gmail API"}],
        facts=["Bulk senders must authenticate outgoing mail."],
    )
    finding, problems = _to_finding(
        draft,
        passport,
        {snapshot.id: snapshot},
        "run_x",
        InvestigationContext(passport, {snapshot.id: snapshot}, {}),
    )
    assert finding.relevance is Relevance.INSUFFICIENT_INFORMATION
    assert any("app-specific impact" in x for x in problems)
    assert finding.validation_issues
