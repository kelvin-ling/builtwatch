"""Builder handoff.

A finding is only useful once it leaves BuiltWatch. Export produces a self-contained
Markdown or JSON document that a person can read or a coding agent can act on, carrying
the evidence with it so the recipient does not have to trust the summary.

Exports state plainly what is fact, what is inference, and what is unknown, and they never
assert a compliance conclusion.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .models import Finding, SystemPassport

DISCLAIMER = (
    "This is a review prompt, not a determination. BuiltWatch reports that an external "
    "development may relate to this system based on the cited passages. It does not "
    "assess compliance, provide legal advice, or verify that the source is current."
)


def to_markdown(finding: Finding, passport: SystemPassport) -> str:
    lines: list[str] = []
    lines.append(f"# {finding.title}")
    lines.append("")
    lines.append(f"**System:** {passport.name} (`{passport.id}`)  ")
    lines.append(f"**Verdict:** {finding.relevance.value}  ")
    lines.append(f"**Adoption status:** {finding.adoption_status.value}  ")
    lines.append(f"**Development key:** `{finding.development_key}`  ")
    lines.append(f"**Finding id:** `{finding.id}`  ")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append("")

    if finding.adoption_status.value == "proposed":
        lines.append(
            "> ⚠️ This development is **proposed**, not adopted. It may change or never "
            "take effect."
        )
        lines.append("")

    lines.append("## Why this system")
    lines.append("")
    if finding.system_facts:
        for ref in finding.system_facts:
            lines.append(f"- `{ref.key}` = {ref.value}")
    else:
        lines.append("- _No specific system fact was cited._")
    lines.append("")

    lines.append("## Evidence")
    lines.append("")
    if finding.evidence:
        for ev in finding.evidence:
            dates = []
            if ev.published_at:
                dates.append(f"published {ev.published_at.isoformat()}")
            if ev.effective_at:
                dates.append(f"effective {ev.effective_at.isoformat()}")
            suffix = f" ({', '.join(dates)})" if dates else ""
            lines.append(f"**Source `{ev.source_id}`{suffix}, snapshot `{ev.snapshot_id}`:**")
            lines.append("")
            for line in ev.passage.strip().splitlines():
                lines.append(f"> {line}")
            lines.append("")
    else:
        lines.append("_No evidence passage was attached._")
        lines.append("")

    for heading, items in (
        ("Facts stated by the source", finding.facts),
        ("Inferences drawn by BuiltWatch", finding.inferences),
        ("Unknowns", finding.unknowns),
        ("Suggested review steps", finding.review_suggestions),
    ):
        lines.append(f"## {heading}")
        lines.append("")
        if items:
            lines.extend(f"- {item}" for item in items)
        else:
            lines.append("_None._")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(DISCLAIMER)
    lines.append("")
    return "\n".join(lines)


def to_json(finding: Finding, passport: SystemPassport) -> str:
    payload = {
        "schema_version": 1,
        "kind": "builtwatch.finding",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "disclaimer": DISCLAIMER,
        "system": {"id": passport.id, "name": passport.name, "purpose": passport.purpose},
        "finding": finding.model_dump(mode="json"),
    }
    return json.dumps(payload, indent=2, default=str)
