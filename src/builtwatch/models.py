"""Core domain models for BuiltWatch.

Design rules encoded here, not just documented:

* A passport records what is *known* and what is explicitly *unknown*. Unknowns are
  first-class so the agent can say "I cannot determine this" instead of guessing.
* Every claim of relevance must carry an evidence passage from a fetched snapshot and
  a matching fact from the system passport. The model makes both mandatory.
* Facts, inferences, unknowns and review suggestions are separate fields. They are
  never merged into one prose blob.
* A development that is only *proposed* is never presented as an adopted requirement.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _norm(text: str) -> str:
    """Normalise text for hashing so trivial whitespace edits do not look like new news."""
    return " ".join(text.split()).strip().lower()


# --------------------------------------------------------------------------------------
# System passport
# --------------------------------------------------------------------------------------


class Provenance(str, Enum):
    """Where a passport field came from. Never inferred silently."""

    USER_STATED = "user_stated"
    AGENT_EXTRACTED = "agent_extracted"
    IMPORTED = "imported"


class ConsequentialAction(BaseModel):
    """Something the system does that has real-world effect if it goes wrong."""

    description: str
    target: str | None = Field(None, description="What it acts on, e.g. 'customer email'.")
    reversible: bool | None = None


class SystemPassport(BaseModel):
    """A versioned description of one system the user has built."""

    schema_version: Literal[1] = 1
    id: str
    name: str
    purpose: str

    technologies: list[str] = Field(default_factory=list)
    services: list[str] = Field(
        default_factory=list, description="External vendors/APIs relied on, e.g. 'Stripe API'."
    )
    consequential_actions: list[ConsequentialAction] = Field(default_factory=list)
    data_categories: list[str] = Field(
        default_factory=list, description="e.g. 'email address', 'health data'."
    )
    assumptions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    jurisdictions: list[str] = Field(
        default_factory=list, description="Optional. Empty means unknown, not global."
    )

    unknowns: list[str] = Field(
        default_factory=list,
        description="Applicability facts that were not determinable. Preserved, never filled in.",
    )
    provenance: dict[str, Provenance] = Field(default_factory=dict)
    source_agent: str | None = Field(
        None,
        max_length=120,
        description="User-visible label for the agent or workspace that supplied this profile.",
    )

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("id")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not v or not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("system id must be a non-empty alphanumeric slug")
        return v

    def fact_index(self) -> dict[str, str]:
        """Flat map of citable facts. The agent may only cite keys that exist here."""
        facts: dict[str, str] = {"purpose": self.purpose}
        for i, t in enumerate(self.technologies):
            facts[f"technologies[{i}]"] = t
        for i, s in enumerate(self.services):
            facts[f"services[{i}]"] = s
        for i, a in enumerate(self.consequential_actions):
            facts[f"consequential_actions[{i}]"] = a.description
        for i, d in enumerate(self.data_categories):
            facts[f"data_categories[{i}]"] = d
        for i, a in enumerate(self.assumptions):
            facts[f"assumptions[{i}]"] = a
        for i, c in enumerate(self.constraints):
            facts[f"constraints[{i}]"] = c
        for i, j in enumerate(self.jurisdictions):
            facts[f"jurisdictions[{i}]"] = j
        return facts


# --------------------------------------------------------------------------------------
# Sources and snapshots
# --------------------------------------------------------------------------------------


class SourceCategory(str, Enum):
    VENDOR_POLICY = "vendor_policy"
    API_CHANGE = "api_change"
    REGULATION = "regulation"
    PRIVACY_AI = "privacy_ai"
    COMMUNICATIONS = "communications"
    SECURITY = "security"
    STANDARDS = "standards"
    BUSINESS_NEWS = "business_news"


class Source(BaseModel):
    """A curated, explicitly listed source. BuiltWatch never watches "the whole world"."""

    id: str
    name: str
    category: SourceCategory
    url: str
    publisher: str
    enabled: bool = True
    notes: str | None = None

    @field_validator("url")
    @classmethod
    def _https_only(cls, v: str) -> str:
        # Registry URLs are the *only* things ever fetched. Enforce https and reject
        # anything that could point at link-local / metadata endpoints.
        if not v.startswith("https://"):
            raise ValueError(f"source url must be https: {v}")
        return v


class FetchStatus(str, Enum):
    OK = "ok"
    HTTP_ERROR = "http_error"
    NETWORK_ERROR = "network_error"
    PARSE_ERROR = "parse_error"
    SKIPPED = "skipped"


class SourceSnapshot(BaseModel):
    """One retrieval of one source at one time. Immutable once stored."""

    id: str
    source_id: str
    retrieved_at: datetime = Field(default_factory=utcnow)
    mode: Literal["live", "replay"] = "live"

    fetch_status: FetchStatus = FetchStatus.OK
    http_status: int | None = None
    error: str | None = None

    content: str = ""
    content_hash: str = ""
    change_context: str = "First observation: existing guidance, not a newly detected change."

    published_at: date | None = None
    effective_at: date | None = None

    def compute_hash(self) -> str:
        return hashlib.sha256(_norm(self.content).encode("utf-8")).hexdigest()

    @property
    def succeeded(self) -> bool:
        return self.fetch_status == FetchStatus.OK and bool(self.content)


# --------------------------------------------------------------------------------------
# Scan runs
# --------------------------------------------------------------------------------------


class SourceHealth(BaseModel):
    """Per-source outcome for one run. This is what stops a failed fetch from looking quiet."""

    source_id: str
    fetch_status: FetchStatus
    http_status: int | None = None
    error: str | None = None
    changed: bool = False
    snapshot_id: str | None = None


class ScanRun(BaseModel):
    id: str
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    mode: Literal["live", "replay"] = "replay"
    status: Literal["running", "complete", "aborted"] = "running"

    source_health: list[SourceHealth] = Field(default_factory=list)
    systems_evaluated: list[str] = Field(default_factory=list)
    # Counts used by the live Impact view. Defaults keep older saved runs readable.
    evaluations_performed: int = 0
    review_events_created: int = 0
    no_action_evaluations: int = 0
    detail_needed_evaluations: int = 0

    model_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    abort_reason: str | None = None
    validation_failures: int = 0

    @property
    def sources_attempted(self) -> int:
        return len(self.source_health)

    @property
    def sources_failed(self) -> list[SourceHealth]:
        return [h for h in self.source_health if h.fetch_status != FetchStatus.OK]

    @property
    def coverage_complete(self) -> bool:
        return not self.sources_failed


# --------------------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------------------


class Relevance(str, Enum):
    RELEVANT = "relevant"
    NOT_RELEVANT = "not_relevant"
    INSUFFICIENT_INFORMATION = "insufficient_information"


class AdoptionStatus(str, Enum):
    """A proposal is not a requirement. Keeping these apart is a correctness property."""

    PROPOSED = "proposed"
    ADOPTED = "adopted"
    IN_EFFECT = "in_effect"
    UNKNOWN = "unknown"


class Evidence(BaseModel):
    """A verbatim passage from a stored snapshot, plus where it came from."""

    snapshot_id: str
    source_id: str
    passage: str = Field(min_length=20, description="Verbatim quote from the snapshot.")
    published_at: date | None = None
    effective_at: date | None = None

    @field_validator("passage")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("evidence passage cannot be blank")
        return v


class SystemFactRef(BaseModel):
    """The passport fact that makes the evidence apply to this system."""

    key: str = Field(description="A key from SystemPassport.fact_index().")
    value: str


class AppImpact(BaseModel):
    """Reasoned consequence anchored to a cited, recorded app fact."""

    fact_key: str = Field(description="Exact key of a system_fact cited in this finding.")
    consequence: str = Field(min_length=20, max_length=600)
    review_question: str = Field(min_length=10, max_length=400)


class Finding(BaseModel):
    id: str
    scan_run_id: str
    system_id: str
    source_id: str

    relevance: Relevance
    title: str
    development_key: str = Field(
        description="Stable identifier for the underlying development, used for dedup."
    )

    evidence: list[Evidence] = Field(default_factory=list)
    system_facts: list[SystemFactRef] = Field(default_factory=list)

    facts: list[str] = Field(default_factory=list, description="Stated by the source.")
    inferences: list[str] = Field(default_factory=list, description="Reasoned, not stated.")
    unknowns: list[str] = Field(default_factory=list, description="Could not be determined.")
    review_suggestions: list[str] = Field(default_factory=list)

    app_impact: AppImpact | None = None
    validation_issues: list[str] = Field(default_factory=list)
    adoption_status: AdoptionStatus = AdoptionStatus.UNKNOWN
    created_at: datetime = Field(default_factory=utcnow)
    revision_hash: str = ""
    quality_version: int = Field(
        default=0,
        description="Assessment-rule generation that produced this. 0 means pre-versioning.",
    )

    def compute_revision_hash(self) -> str:
        """Material revision: changes only when the substance changes."""
        material = "|".join(
            [
                self.system_id,
                self.development_key,
                self.adoption_status.value,
                *sorted(_norm(e.passage) for e in self.evidence),
                *sorted(_norm(f) for f in self.facts),
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def dedup_key(self) -> str:
        return f"{self.system_id}::{self.development_key}"

    def validate_grounding(self, passport: SystemPassport) -> list[str]:
        """Structural check that a relevance claim is actually grounded.

        Returns a list of problems. An empty list means the finding may be surfaced.
        """
        problems: list[str] = []
        if self.relevance is Relevance.RELEVANT:
            if not self.evidence:
                problems.append("relevant finding has no evidence passage")
            if not self.system_facts:
                problems.append("relevant finding cites no system fact")
            if not self.facts:
                # Without a stated fact there is nothing the source actually says — only
                # the model's own reasoning, which is not grounds to interrupt someone.
                problems.append("relevant finding states no fact from the source")
        if self.app_impact and self.app_impact.fact_key not in {r.key for r in self.system_facts}:
            problems.append("app impact is not anchored to a cited system fact")
        index = passport.fact_index()
        for ref in self.system_facts:
            if ref.key not in index:
                problems.append(f"cited system fact key does not exist: {ref.key}")
            elif _norm(index[ref.key]) != _norm(ref.value):
                problems.append(f"cited system fact value does not match passport: {ref.key}")
        return problems


class DispositionAction(str, Enum):
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    EXPORTED = "exported"


class AgentReviewOutcome(str, Enum):
    NO_CHANGE_NEEDED = "no_change_needed"
    APP_UPDATED = "app_updated"
    NEEDS_HUMAN_DECISION = "needs_human_decision"
    UNABLE_TO_VERIFY = "unable_to_verify"


class AgentReview(BaseModel):
    finding_id: str
    system_id: str
    outcome: AgentReviewOutcome
    summary: str = Field(min_length=1, max_length=1000)
    created_at: datetime = Field(default_factory=utcnow)


class Disposition(BaseModel):
    id: str
    finding_id: str
    action: DispositionAction
    reason: str | None = None
    actor: str = "user"
    created_at: datetime = Field(default_factory=utcnow)
