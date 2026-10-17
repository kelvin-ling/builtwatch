"""Zero-inference change matching. Matches are review candidates, never impact verdicts.

Only additions to an established snapshot can create a candidate. Exact passages and
recorded dependency facts travel together; interpretation stays with the human or their
existing project agent. Regulatory applicability is outside this matcher's scope.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from typing import TYPE_CHECKING

from .models import (
    AppImpact,
    Evidence,
    Finding,
    Relevance,
    Source,
    SourceCategory,
    SourceSnapshot,
    SystemFactRef,
    SystemPassport,
)
from .store import new_id

if TYPE_CHECKING:
    from .agent.relevance import ScreenVerdict

ENGINE = "rules-v2"
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


# Only feeds dedicated to a product can route a passage that omits its name.
DEDICATED_SOURCES = frozenset(
    {
        "anthropic-aup",
        "aws-bedrock-history",
        "gmail-sender-guidelines",
        "stripe-upgrades",
        "twilio-changelog",
        "github-rest-breaking",
    }
)
PRODUCT_ALIASES = (
    ("microsoft graph api", "microsoft graph", "ms graph"),
    ("azure openai", "azure openai service"),
    ("cloudflare workers", "workers runtime"),
    ("amazon bedrock", "aws bedrock", "bedrock"),
    ("gmail api", "gmail"),
    ("node.js", "nodejs"),
    ("next.js", "nextjs"),
    ("openai api", "openai"),
    ("google gemini", "gemini", "google ai"),
    ("anthropic", "claude"),
)
MAX_CANDIDATES = 50


def dependency_aliases(value: str) -> tuple[str, ...]:
    """Use whole product names; a shared word is not proof of product identity."""
    from .quality import GENERIC_TERMS, MIN_TERM_LENGTH

    groups = [
        (max(len(a) for a in group if _has(value, a)), group)
        for group in PRODUCT_ALIASES
        if any(_has(value, a) for a in group)
    ]
    if groups:
        return max(groups, key=lambda item: item[0])[1]
    name = re.sub(r"\s+(?:v?\d[\w.*-]*)(?:\s.*)?$", "", value.strip(), flags=re.I)
    name = re.sub(r"\s+(?:API|SDK)$", "", name, flags=re.I).strip()
    return (name,) if len(name) >= MIN_TERM_LENGTH and name.lower() not in GENERIC_TERMS else ()


def dependency_refs(passport: SystemPassport, passage: str, source: Source) -> list[SystemFactRef]:
    refs = []
    for key, value in passport.fact_index().items():
        if not key.startswith(("services[", "technologies[")):
            continue
        aliases = dependency_aliases(value)
        mentioned = any(_has(passage, alias) for alias in aliases)
        # In a product-specific feed, the publisher supplies context. A broad
        # vendor changelog or security feed cannot transfer scope across products.
        routed = (
            source.id in DEDICATED_SOURCES
            and source.category is not SourceCategory.SECURITY
            and any(_has(value, alias) for alias in SOURCE_TERMS.get(source.id, ()))
        )
        scoped = (
            source.id == "cloudflare-changelog"
            and "cloudflare workers" in aliases
            and _has(passage, "workers")
        )
        if mentioned or routed or scoped:
            refs.append(SystemFactRef(key=key, value=value))
    return refs


def _matches(
    passport: SystemPassport, snapshot: SourceSnapshot, source: Source
) -> Iterator[tuple[str, list[SystemFactRef]]]:
    seen = set()
    for line in snapshot.added_passages:
        if line not in snapshot.content:
            continue
        # Overlapping exact windows preserve long changed paragraphs without
        # silently dropping developments after the first 1,200 characters.
        for start in range(0, len(line), MAX_PASSAGE - 200):
            passage = line[start : start + MAX_PASSAGE]
            canonical = " ".join(passage.lower().split())
            if (
                len(passage.strip()) < MIN_PASSAGE
                or not MATERIAL.search(passage)
                or canonical in seen
            ):
                continue
            refs = dependency_refs(passport, passage, source)
            if refs:
                seen.add(canonical)
                yield passage, refs


def screen(passport: SystemPassport, snapshot: SourceSnapshot, source: Source) -> ScreenVerdict:
    from .agent.relevance import ScreenVerdict

    match = next(_matches(passport, snapshot, source), None)
    return ScreenVerdict(
        plausible="possible" if match else "no",
        reason=(
            "A changed passage matches a recorded dependency; review required."
            if match
            else "No dependency match in added passages. This is not an applicability assessment."
        ),
    )


def assess(
    passport: SystemPassport,
    snapshots: dict[str, SourceSnapshot],
    sources: dict[str, Source],
    scan_run_id: str,
) -> tuple[list[Finding], list[str]]:
    from .config import BudgetExceeded

    findings, problems = [], []
    for snapshot in snapshots.values():
        source = sources[snapshot.source_id]
        for passage, refs in _matches(passport, snapshot, source):
            if len(findings) >= MAX_CANDIDATES:
                raise BudgetExceeded("Rule candidate ceiling reached; coverage is incomplete.")
            finding, issues = _finding(passport, snapshot, source, scan_run_id, passage, refs)
            findings.append(finding)
            problems.extend(issues)
    return findings, problems


def _finding(
    passport: SystemPassport,
    snapshot: SourceSnapshot,
    source: Source,
    scan_run_id: str,
    passage: str,
    refs: list[SystemFactRef],
) -> tuple[Finding, list[str]]:
    key, value = refs[0].key, refs[0].value
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
            + hashlib.sha256(" ".join(passage.lower().split()).encode()).hexdigest()[:20]
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
        system_facts=refs,
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
