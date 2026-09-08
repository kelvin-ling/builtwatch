"""Exports must carry their evidence and must never overclaim."""

from __future__ import annotations

from conftest import make_finding

from builtwatch.export import DISCLAIMER, to_json, to_markdown
from builtwatch.models import AdoptionStatus, Relevance


def test_markdown_carries_evidence_and_matched_fact(passport, snapshot):
    md = to_markdown(make_finding(passport, snapshot), passport)
    assert "Gmail bulk sender requirements" in md
    assert "> " in md, "evidence passage should be block-quoted"
    assert "services[0]" in md
    assert DISCLAIMER in md


def test_proposed_status_is_flagged_prominently(passport, snapshot):
    finding = make_finding(passport, snapshot)
    finding.adoption_status = AdoptionStatus.PROPOSED
    md = to_markdown(finding, passport)
    assert "**proposed**, not adopted" in md


def test_adopted_status_gets_no_proposal_warning(passport, snapshot):
    finding = make_finding(passport, snapshot)
    finding.adoption_status = AdoptionStatus.ADOPTED
    assert "not adopted" not in to_markdown(finding, passport)


def test_sections_stay_separate(passport, snapshot):
    finding = make_finding(passport, snapshot)
    finding.inferences = ["This probably applies to the morning send."]
    finding.unknowns = ["Current daily send volume is not recorded."]
    md = to_markdown(finding, passport)
    assert "## Facts stated by the source" in md
    assert "## Inferences drawn by BuiltWatch" in md
    assert "## Unknowns" in md
    assert md.index("## Facts stated by the source") < md.index("## Inferences drawn by BuiltWatch")


def test_json_export_is_machine_readable(passport, snapshot):
    import json

    payload = json.loads(to_json(make_finding(passport, snapshot), passport))
    assert payload["schema_version"] == 1
    assert payload["kind"] == "builtwatch.finding"
    assert payload["system"]["id"] == "inbox-triage"
    assert payload["finding"]["relevance"] == Relevance.RELEVANT.value
    assert payload["finding"]["evidence"][0]["passage"]
    assert payload["disclaimer"] == DISCLAIMER


def test_insufficient_information_export_names_the_gap(passport, snapshot):
    finding = make_finding(passport, snapshot, relevance=Relevance.INSUFFICIENT_INFORMATION)
    finding.unknowns = ["Jurisdiction was never recorded for this system."]
    md = to_markdown(finding, passport)
    assert "insufficient_information" in md
    assert "Jurisdiction was never recorded" in md
