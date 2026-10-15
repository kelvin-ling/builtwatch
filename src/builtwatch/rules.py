"""Zero-inference change matching. Matches are review candidates, never impact verdicts.

Only additions to an established snapshot can create a candidate. Exact passages and
recorded dependency facts travel together; interpretation stays with the human or their
existing project agent. Regulatory applicability is outside this matcher's scope.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .models import (
    AppImpact,
    Evidence,
    Finding,
    Relevance,
    SourceCategory,
    SystemFactRef,
    SystemPassport,
)
from .store import new_id

ENGINE = "rules-v1"
# Curated registry routing, not inferred dependencies. Broad security feeds require a
# product name in the changed passage itself instead of a publisher-level match.
SOURCE_TERMS = {
    "anthropic-aup": ("anthropic", "claude"),
    "aws-bedrock-history": ("bedrock", "nova"),
    "aws-security-bulletins": ("aws", "amazon web services", "bedrock"),
    "openai-api-changelog": ("openai",),
    "google-gemini-changelog": ("gemini", "google ai"),
    "azure-openai-whats-new": ("azure openai",),
    "cloudflare-changelog": ("cloudflare",),
    "github-rest-breaking": ("github",),
    "github-advisories": ("github",),
    "stripe-upgrades": ("stripe",),
    "twilio-changelog": ("twilio",),
    "gmail-sender-guidelines": ("gmail",),
    "vercel-changelog": ("vercel", "next.js"),
    "nodejs-releases": ("node.js", "nodejs"),
}
MATERIAL = re.compile(
    r"\b(?:CVE-\d|deprecat\w*|retir\w*|remov\w*|breaking|vulnerabilit\w*|"
    r"must|requir\w*|no longer|end of (?:life|support)|limit\w*|pricing|"
    r"security|migration|discontinu\w*)",
    re.IGNORECASE,
)
MIN_PASSAGE = 20
MAX_PASSAGE = 1200
MAX_PURPOSE = 600


def _has(text: str, term: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.IGNORECASE))


def _match(passport: SystemPassport, snapshot: Any, source: Any) -> tuple[str, str, str] | None:
    from .quality import _tokens

    dependencies = {
        key: value
        for key, value in passport.fact_index().items()
        if key.startswith(("services[", "technologies["))
    }
    for line in snapshot.added_passages:
        if len(line.strip()) < MIN_PASSAGE or not MATERIAL.search(line):
            continue
        # A changed item must really be in this snapshot, even if called outside the pipeline.
        if line not in snapshot.content:
            continue
        for key, value in dependencies.items():
            aliases = SOURCE_TERMS.get(source.id, ())
            routed = any(_has(value, alias) for alias in aliases)
            tokens = _tokens(value)
            mentioned = any(_has(line, term) for term in tokens)
            if not (mentioned or (routed and source.category is not SourceCategory.SECURITY)):
                continue
            # Bound around the signal rather than accidentally quoting only navigation.
            signal = MATERIAL.search(line)
            start = max(0, signal.start() - 200)
            return key, value, line[start : start + MAX_PASSAGE]
    return None


def screen(passport: SystemPassport, snapshot: Any, source: Any) -> Any:
    from .agent.relevance import ScreenVerdict

    match = _match(passport, snapshot, source)
    return ScreenVerdict(
        plausible="possible" if match else "no",
        reason=(
            "A changed passage matches a recorded dependency; review required."
            if match
            else "No dependency match in added passages. This is not an applicability assessment."
        ),
    )


def assess(passport: SystemPassport, snapshots: dict, sources: dict, scan_run_id: str) -> tuple:
    snapshot = next(iter(snapshots.values()))
    source = sources[snapshot.source_id]
    match = _match(passport, snapshot, source)
    if match is None:
        return None, ["No verifiable changed passage matched a recorded dependency."]
    key, value, passage = match
    finding = Finding(
        id=new_id("find"),
        scan_run_id=scan_run_id,
        system_id=passport.id,
        source_id=source.id,
        relevance=Relevance.RELEVANT,
        assessment_method=ENGINE,
        title=f"Review a source change connected to {value}"[:160],
        development_key=(
            f"rules:{source.id}:"
            + hashlib.sha256(" ".join(passage.split()).encode()).hexdigest()[:20]
        ),
        evidence=[
            Evidence(
                snapshot_id=snapshot.id,
                source_id=source.id,
                passage=passage,
                published_at=snapshot.published_at,
                effective_at=snapshot.effective_at,
            )
        ],
        system_facts=[SystemFactRef(key=key, value=value)],
        facts=[passage],
        inferences=[
            f"A changed source passage matched the recorded dependency '{value}'. "
            "This is a rule-based review candidate; impact has not been assessed."
        ],
        unknowns=[
            "Whether the change affects the app's actual usage, version or configuration.",
            "Legal applicability and adoption status have not been determined.",
        ],
        review_suggestions=[
            "Check the quoted change against the app, or ask your existing "
            "project agent to investigate before making changes."
        ],
        app_impact=AppImpact(
            fact_key=key,
            consequence=f"The app records '{value}'. A matching source passage changed; "
            "a person must establish whether this affects the app.",
            review_question=f"Does this quoted change affect how {passport.name} uses {value}?",
        ),
    )
    problems = finding.validate_grounding(passport)
    if problems:
        finding.relevance = Relevance.INSUFFICIENT_INFORMATION
        finding.validation_issues = problems
    finding.revision_hash = finding.compute_revision_hash()
    return finding, problems


def draft_profile(description: str, system_id: str | None = None) -> SystemPassport:
    """Preserve the supplied description and extract only literal named dependencies."""
    from .intake import _slugify

    name = description.strip().splitlines()[0][:100].strip() or "My app"
    services = [
        alias for terms in SOURCE_TERMS.values() for alias in terms if _has(description, alias)
    ]
    technologies = [
        name
        for name in ("Python", "JavaScript", "TypeScript", "React", "Node.js")
        if _has(description, name)
    ]
    return SystemPassport(
        id=system_id or _slugify(name),
        name=name,
        purpose=description.strip()[:MAX_PURPOSE],
        services=list(dict.fromkeys(services)),
        technologies=technologies,
        unknowns=[
            "This draft uses literal name matching without AI. Review every field; "
            "actions, data, jurisdictions and operating conditions are not inferred."
        ]
        + (
            [
                "The description was longer than 600 characters; import an agent-prepared "
                "profile to preserve its full structured context."
            ]
            if len(description) > MAX_PURPOSE
            else []
        ),
    )
