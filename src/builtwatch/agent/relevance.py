"""The two-stage relevance investigation.

Stage 1 (screen) is a cheap, high-recall filter on a small model with no tools. It exists
because the expensive stage should only ever run on plausible pairs — that is what keeps
a nightly scan close to free.

Stage 2 (assess) is a bounded, tool-using Strands agent on a stronger model. It must read
the passport and the evidence through tools before it can produce a finding, and its
structured output is validated against the passport before anything is stored.

A draft that fails grounding validation is downgraded, never surfaced as-is. That is the
difference between an agent that cites evidence and an agent that says it cites evidence.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field
from strands import Agent
from strands.models import BedrockModel

from ..config import BudgetExceeded, CostMeter, Settings
from ..models import (
    AdoptionStatus,
    Evidence,
    Finding,
    Relevance,
    Source,
    SourceSnapshot,
    SystemFactRef,
    SystemPassport,
)
from ..store import new_id
from .guard import BudgetGuard
from .prompts import ASSESS_SYSTEM_PROMPT, SCREEN_SYSTEM_PROMPT
from .tools import InvestigationContext, build_tools

logger = logging.getLogger(__name__)
MIN_EVIDENCE_LENGTH = 20


class ScreenVerdict(BaseModel):
    """Cheap first-pass answer."""

    plausible: Literal["yes", "possible", "no"]
    reason: str = Field(max_length=400)


class DraftEvidence(BaseModel):
    passage_id: str | None = Field(
        default=None,
        description="ID of the exact <passage> you read. Prefer selecting an ID to retyping text.",
    )
    snapshot_id: str = ""
    passage: str = Field(
        default="", description="Legacy fallback: exact quote, only when passage_id is unavailable."
    )


class DraftSystemFact(BaseModel):
    key: str = Field(description="An exact key from the passport's fact_index.")
    value: str = Field(description="The exact value for that key.")


class FindingDraft(BaseModel):
    """What the assessment agent must produce. Validated before it becomes a Finding."""

    relevance: Literal["relevant", "not_relevant", "insufficient_information"]
    title: str = Field(max_length=160)
    development_key: str = Field(
        max_length=120,
        description="Stable slug for the underlying development, e.g. 'eu-ai-act-transparency'.",
    )
    adoption_status: Literal["proposed", "adopted", "in_effect", "unknown"] = "unknown"

    evidence: list[DraftEvidence] = Field(default_factory=list)
    system_facts: list[DraftSystemFact] = Field(default_factory=list)

    facts: list[str] = Field(default_factory=list, description="Stated by the source.")
    inferences: list[str] = Field(default_factory=list, description="Your reasoning.")
    unknowns: list[str] = Field(default_factory=list, description="Not determinable.")
    review_suggestions: list[str] = Field(default_factory=list)


def _bedrock(settings: Settings, model_id: str) -> BedrockModel:
    return BedrockModel(
        model_id=model_id,
        region_name=settings.region,
        max_tokens=settings.limits.max_output_tokens,
        temperature=0.2,
    )


def screen(
    passport: SystemPassport,
    snapshot: SourceSnapshot,
    source: Source,
    settings: Settings,
    meter: CostMeter,
) -> ScreenVerdict:
    """Stage 1. Returns a verdict; on budget abort, fails open to 'possible'."""
    from ..quality import source_out_of_scope

    if source_out_of_scope(passport, source.id):
        return ScreenVerdict(plausible="no", reason="This vendor is not a recorded dependency.")
    guard = BudgetGuard(meter, settings.screen_model_id, max_iterations=2)
    agent = Agent(
        model=_bedrock(settings, settings.screen_model_id),
        system_prompt=SCREEN_SYSTEM_PROMPT,
        hooks=[guard],
        callback_handler=None,
        structured_output_model=ScreenVerdict,
    )
    excerpt = snapshot.content[:3000]
    prompt = (
        f"SYSTEM PROFILE\n"
        f"  name: {passport.name}\n"
        f"  purpose: {passport.purpose}\n"
        f"  technologies: {', '.join(passport.technologies) or '(none recorded)'}\n"
        f"  external services: {', '.join(passport.services) or '(none recorded)'}\n"
        f"  data categories: {', '.join(passport.data_categories) or '(none recorded)'}\n"
        f"  jurisdictions: {', '.join(passport.jurisdictions) or '(not recorded)'}\n\n"
        f"OBSERVATION CONTEXT (untrusted): {snapshot.change_context}\n\n"
        f"EXTERNAL DEVELOPMENT from {source.publisher} ({source.category.value})\n"
        f'<evidence snapshot_id="{snapshot.id}">\n{excerpt}\n</evidence>\n\n'
        f"Could this development plausibly affect this system?"
    )
    try:
        result = agent(prompt)
    finally:
        # Charge whatever was consumed even if the call raised part-way through.
        guard.reconcile(agent)
    verdict = result.structured_output
    if verdict is None:
        # A model that failed to produce the schema must not silently drop the pair.
        return ScreenVerdict(plausible="possible", reason="screening produced no verdict")
    return verdict


def assess(
    passport: SystemPassport,
    snapshots: dict[str, SourceSnapshot],
    sources: dict[str, Source],
    scan_run_id: str,
    settings: Settings,
    meter: CostMeter,
) -> tuple[Finding | None, list[str]]:
    """Stage 2. Returns (finding, problems).

    ``problems`` is non-empty when the draft failed grounding validation. In that case the
    finding is returned downgraded to insufficient_information rather than discarded, so
    the failure is visible instead of looking like silence.
    """
    ctx = InvestigationContext(
        passport=passport,
        snapshots=snapshots,
        sources=sources,
        max_passage_chars=settings.limits.max_passage_chars,
    )
    guard = BudgetGuard(
        meter, settings.assess_model_id, max_iterations=settings.limits.max_agent_iterations
    )
    agent = Agent(
        model=_bedrock(settings, settings.assess_model_id),
        system_prompt=ASSESS_SYSTEM_PROMPT,
        tools=build_tools(ctx),
        hooks=[guard],
        callback_handler=None,
        structured_output_model=FindingDraft,
    )

    listing = "\n".join(
        f"  - {snap.id}: {sources[snap.source_id].name} "
        f"({sources[snap.source_id].publisher}, {sources[snap.source_id].category.value})"
        for snap in snapshots.values()
        if snap.source_id in sources
    )
    prompt = (
        f"Assess system '{passport.id}' ({passport.name}).\n\n"
        f"Evidence documents available this run:\n{listing}\n\n"
        f"Observation context (untrusted):\n"
        + "\n".join(s.change_context for s in snapshots.values())
        + "\nFirst observations establish a baseline: do not call standing policy a new change. "
        "For subsequent observations, focus on the difference, not unchanged requirements. "
        "If only navigation or formatting changed, return not_relevant. "
        "Read the passport, read the evidence, then produce your finding."
    )

    try:
        result = agent(prompt)
    except BudgetExceeded:
        guard.reconcile(agent)
        raise
    except Exception as exc:
        guard.reconcile(agent)
        logger.warning("assessment failed for %s: %s", passport.id, exc)
        return None, [f"assessment error: {type(exc).__name__}: {exc}"]
    else:
        guard.reconcile(agent)

    draft = result.structured_output
    if draft is None:
        return None, ["assessment produced no structured finding"]
    if not ctx.reads:
        # The agent answered without opening a single document. Whatever it produced is
        # not grounded in evidence, by definition.
        return None, ["assessment answered without reading any evidence"]

    return _to_finding(draft, passport, snapshots, scan_run_id, ctx)


def _to_finding(
    draft: FindingDraft,
    passport: SystemPassport,
    snapshots: dict[str, SourceSnapshot],
    scan_run_id: str,
    ctx: InvestigationContext,
) -> tuple[Finding, list[str]]:
    """Convert a draft into a Finding, verifying every citation against stored data."""
    problems: list[str] = []

    evidence: list[Evidence] = []
    for draft_item in draft.evidence:
        item = draft_item
        if item.passage_id:
            selected = ctx.passages.get(item.passage_id)
            if selected is None:
                problems.append("selected evidence passage was not read")
                continue
            item = DraftEvidence(snapshot_id=selected[0], passage=selected[1])
        snap = snapshots.get(item.snapshot_id)
        if snap is None:
            problems.append(f"cited snapshot does not exist: {item.snapshot_id}")
            continue
        # The quoted passage must actually appear in the stored snapshot. This is the
        # check that catches a fabricated quote.
        if len(item.passage.strip()) < MIN_EVIDENCE_LENGTH or _norm_space(
            item.passage
        ) not in _norm_space(snap.content):
            problems.append(f"quoted passage not found verbatim in snapshot {item.snapshot_id}")
            continue
        evidence.append(
            Evidence(
                snapshot_id=snap.id,
                source_id=snap.source_id,
                passage=item.passage[: ctx.max_passage_chars],
                published_at=snap.published_at,
                effective_at=snap.effective_at,
            )
        )

    system_facts = [SystemFactRef(key=f.key, value=f.value) for f in draft.system_facts]

    primary_source = evidence[0].source_id if evidence else next(iter(snapshots.values())).source_id
    finding = Finding(
        id=new_id("find"),
        scan_run_id=scan_run_id,
        system_id=passport.id,
        source_id=primary_source,
        relevance=Relevance(draft.relevance),
        title=draft.title,
        development_key=draft.development_key,
        evidence=evidence,
        system_facts=system_facts,
        facts=draft.facts,
        inferences=draft.inferences,
        unknowns=draft.unknowns,
        review_suggestions=draft.review_suggestions,
        adoption_status=AdoptionStatus(draft.adoption_status),
    )

    problems.extend(finding.validate_grounding(passport))

    from ..quality import dependency_mismatch

    if primary_source == "cisa-kev" and dependency_mismatch(
        passport, " ".join([finding.title, *finding.facts, *finding.inferences])
    ):
        finding.relevance = Relevance.NOT_RELEVANT
        finding.inferences = ["The affected product is not a recorded dependency of this system."]
        finding.unknowns = []
        finding.review_suggestions = []
    finding.validation_issues = problems
    if problems and finding.relevance is Relevance.RELEVANT:
        # An ungrounded "relevant" claim is downgraded, not published. The reason is
        # attached so a reviewer can see the model over-reached.
        finding.relevance = Relevance.INSUFFICIENT_INFORMATION
        finding.unknowns.append(
            "Downgraded automatically: the relevance claim was not grounded "
            "and was withheld from action items."
        )

    finding.revision_hash = finding.compute_revision_hash()
    return finding, problems


def _norm_space(text: str) -> str:
    return " ".join(text.split())
