"""Review headings say what kind of change it is, what it names, and when it takes effect."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from conftest import make_finding

from builtwatch.config import Settings
from builtwatch.deadlines import in_text
from builtwatch.export import to_markdown
from builtwatch.models import Evidence, SourceSnapshot
from builtwatch.rules import ENGINE, GENERIC_TITLE, assess, review_title
from builtwatch.web_api import dispatch

CASES = json.loads((Path(__file__).parent / "fixtures/take_effect_cases.json").read_text())


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["text"][:40])
def test_take_effect_dates_match_the_browser_reader(case):
    # web/deadlines.js is held to the same cases, so browser and server read dates alike.
    found = [[x.on.isoformat(), x.phrase] for x in in_text(case["text"])]
    assert found == case["dates"]


def evidence(passage, **extra):
    return Evidence(snapshot_id="snap", source_id="feed", passage=passage, **extra)


@pytest.mark.parametrize(
    ("passage", "title"),
    [
        (
            "The v1 Charges endpoint is deprecated and will be removed on June 30th, 2027.",
            "Deprecation or removal · Stripe API · effective Jun 30, 2027",
        ),
        (
            "CVE-2026-1234: a vulnerability in Node.js lets a crafted request crash the server.",
            "Security issue · Node.js",
        ),
        (
            "This is a breaking change: webhook payloads no longer include the legacy field.",
            "Breaking change · Stripe API",
        ),
        (
            "From 1 February 2026, bulk senders must authenticate outgoing mail.",
            "New requirement · Gmail API · effective Feb 1, 2026",
        ),
        (
            "Pricing for batch requests is now billed per thousand tokens.",
            "Pricing change · OpenAI API",
        ),
        ("Default rate limits for new projects are lower.", "Limit change · OpenAI API"),
        ("Migrate webhooks to the v2 signing secret.", "Migration · Twilio"),
        ("Webhook security settings were reorganised in the dashboard.", "Change · Twilio"),
        (
            "Remove repository detail fields from migration resource responses",
            "Deprecation or removal · GitHub REST API",
        ),
        (
            "Removed the legacy charges field from webhook payloads.",
            "Deprecation or removal · Stripe API",
        ),
        (
            "No action is required for customers with Fraud Guard enabled; limits rise.",
            "Limit change · Twilio",
        ),
        ("No code changes are required; quotas rise next week.", "Limit change · Twilio"),
    ],
)
def test_heading_names_the_kind_of_change_and_its_dependency(passage, title):
    assert review_title(evidence(passage), title.split(" · ")[1]) == title


def test_a_heading_carries_a_date_only_when_it_is_unambiguous():
    recorded = evidence("Starting February 1, 2024, senders must.", effective_at=date(2024, 6, 1))
    assert review_title(recorded, "Gmail API").endswith("effective Jun 1, 2024")
    # Two stated dates: which one matters depends on the day, so neither goes in a
    # stored heading. The passage itself is still on the card.
    two = evidence("Starting November 1, 2026, v1 is retired. Effective January 15, 2027, too.")
    assert review_title(two, "Stripe API") == "Deprecation or removal · Stripe API"
    long_name = "Payments platform " * 10
    assert review_title(recorded, long_name).endswith(" · effective Jun 1, 2024")


def test_new_rule_matches_get_a_specific_heading(passport, snapshot, source):
    current = SourceSnapshot(
        id="snap_new",
        source_id=source.id,
        content=snapshot.content,
        added_passages=[snapshot.content],
    )
    findings, _ = assess(passport, {current.id: current}, {source.id: source}, "run_titles")
    assert findings
    title = findings[0].title
    assert not title.startswith(GENERIC_TITLE)
    assert title == "New requirement · Gmail API · effective Feb 1, 2026"
    assert findings[0].evidence[0].passage in snapshot.content  # still verbatim evidence


def test_stored_generic_headings_are_rebuilt_on_read_without_rewriting_history(
    store, passport, snapshot
):
    store.upsert_system(passport)
    legacy = make_finding(passport, snapshot, finding_id="find_legacy")
    legacy.assessment_method = ENGINE
    legacy.title = GENERIC_TITLE + "Gmail API"
    stored_hash = legacy.compute_revision_hash()
    store.save_finding(legacy)
    store.save_finding(make_finding(passport, snapshot, finding_id="find_ai", development_key="ai"))

    event = {"rawPath": "/api/workspace", "requestContext": {"http": {"method": "GET"}}}
    result = dispatch(event, store, Settings(), None, verified=True)
    titles = {f["id"]: f["title"] for f in json.loads(result["body"])["findings"]}

    assert titles["find_legacy"] == "New requirement · Gmail API · effective Feb 1, 2026"
    assert titles["find_ai"] == "Gmail bulk sender requirements"  # assessed headings stay
    saved = store.get_finding("find_legacy")
    assert saved.title == GENERIC_TITLE + "Gmail API"
    assert saved.compute_revision_hash() == stored_hash  # dedup identity unchanged
    assert to_markdown(saved, passport).startswith("# New requirement · Gmail API")
