from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_demo_contains_only_examples_and_real_replay_results():
    data = json.loads((ROOT / "web/demo.json").read_text())
    allowed = {p.stem for p in (ROOT / "examples/passports").glob("*.json")}
    assert data["demo"] is True
    assert {s["id"] for s in data["systems"]} <= allowed
    assert data["findings"]
    assert {f["system_id"] for f in data["findings"]} <= allowed
    assert all(r["mode"] == "replay" for r in data["runs"])


def test_frontend_does_not_embed_owner_secret():
    for path in (ROOT / "web").iterdir():
        if path.is_file():
            text = path.read_text()
            assert "BW_OWNER_TOKEN" not in text
            assert "workspace-access.json" not in text
    assert "prefers-reduced-motion" in (ROOT / "web/style.css").read_text()
    assert 'aria-labelledby="modal-title"' in (ROOT / "web/index.html").read_text()


def test_frontend_copy_does_not_reference_chat_accounts_or_model_brands():
    app = (ROOT / "web/app.js").read_text()
    demo = (ROOT / "web/demo.json").read_text()

    assert "No ChatGPT account" not in app
    assert "Claude" not in demo


def test_live_links_use_the_preferred_custom_domain():
    app = (ROOT / "web/app.js").read_text()
    accounts = (ROOT / "docs/ACCOUNTS.md").read_text()
    monitor = (ROOT / "infra/cost_monitor.py").read_text()

    for text in (app, accounts, monitor):
        assert "https://builtwatch.org" in text
        assert "builtwatch.kelvinlingac.chatgpt.site" not in text


def test_completed_checks_do_not_create_a_global_status_banner():
    app = (ROOT / "web/app.js").read_text()
    notice = app[app.index("function jobNotice()") : app.index("function render()")]

    assert "state.job.status!=='idle'" not in app
    assert "function jobNotice()" in app
    assert "complete:'" not in notice


def test_dialog_focus_and_actions_are_safe_on_small_screens():
    app = (ROOT / "web/app.js").read_text()
    css = (ROOT / "web/style.css").read_text()

    assert '<h2 id="modal-title" tabindex="-1">' in app
    assert "$('#modal-title').focus({preventScroll:true})" in app
    assert ".modal-head h2:focus{outline:none}" in css
    assert "margin:24px -28px -26px" not in css
    assert ".modal-actions:not(.modal-footer){display:grid!important" in css
    assert ".modal-body{flex:1 1 auto;overflow-y:auto" in css
    assert "content.classList.toggle('has-footer',Boolean(actions))" in app
    assert "const actions=$('.modal-body .modal-actions')" in app
    assert "modalBody.scrollTop=0" in app
    assert "button.setAttribute('form',actionForm.id)" in app
    assert "#modal-content.has-footer{height:90dvh}" in css
    assert "#modal-content.has-footer{height:calc(90dvh - 2px)}" in css
    assert "env(safe-area-inset-bottom)" in css
    assert ".modal-actions:not(.modal-footer){grid-template-columns:1fr}" in css


def test_bulk_import_note_stays_above_its_submit_button():
    app = (ROOT / "web/app.js").read_text()
    start = app.index("function bulkImport(){")
    bulk = app[start : app.index("\nfunction ", start + 10)]

    assert bulk.index('class="section-note"') < bulk.index('class="modal-actions"')


def test_bulk_import_keeps_export_when_returning_from_review():
    app = (ROOT / "web/app.js").read_text()

    assert "let adminData=null,bulkProfiles=[],bulkInput=''" in app
    assert 'textarea id="bulk-json" required maxlength="24000" placeholder=\'{"systems":[...]}\' spellcheck="false">${esc(bulkInput)}</textarea>' in app
    assert "bulkInput=$('#bulk-json').value" in app
    assert "if(e.target.id==='bulk-json')bulkInput=e.target.value" in app


def test_agent_import_is_primary_and_profiles_show_their_source():
    app = (ROOT / "web/app.js").read_text()
    css = (ROOT / "web/style.css").read_text()

    assert "Import from agent" in app
    assert "Import one app from your agent" in app
    assert "Import several apps from your agent" in app
    assert "Describe the agent, automation, API integration, or app" not in app
    assert "source_agent" in app
    assert "Imported from ${esc(s.source_agent)}" in app
    add_flow = app[app.index("function add(") : app.index("function reviewDraft(")]
    assert "Agent or workspace name" not in add_flow
    assert "data-action=\"copy-builder\"" in add_flow
    assert "Paste profile JSON" not in add_flow
    assert "visual-import" in app
    assert ".source-badge" in css
    assert "@keyframes agent-import-row" in css


def test_profiles_expose_remove_action_without_hiding_it_in_more_options():
    app = (ROOT / "web/app.js").read_text()
    start = app.index("function profile(")
    profile = app[start : app.index("\nfunction editContext", start)]

    assert 'data-delete="${esc(id)}">Remove app' in profile
    assert profile.index('data-delete="${esc(id)}"') < profile.index('<details class="modal-more">')


def test_unsigned_demo_can_complete_the_review_flow_in_place():
    app = (ROOT / "web/app.js").read_text()
    css = (ROOT / "web/style.css").read_text()

    assert "state.demo?'Preview agent handoff':esc(route.cta)" in app
    assert "Preview the agent handoff" in app
    assert "Copy prompt for my agent" in app
    assert "Record outcome instead" in app
    assert "!state.demo&&f.disposition==='open'" not in app
    assert 'class="group-title"' in app
    assert 'class="system-mini-copy"' in app
    assert ".app-finding-group>summary span.group-title:first-child{display:grid" in css


def test_review_outcomes_are_explicit_and_agent_handoff_is_optional():
    app = (ROOT / "web/app.js").read_text()
    css = (ROOT / "web/style.css").read_text()

    assert "function recordOutcome(" in app
    assert "Sending this to an agent is optional." in app
    for label in (
        "No app change needed",
        "The app was updated",
        "This does not apply",
        "Keep this open",
    ):
        assert label in app
    assert "Nothing closes until you record the outcome." in app
    assert "data-record-outcome" in app
    assert ".outcome-options" in css
    assert ".agent-review-result" in css


def test_reviews_show_whether_an_agent_or_human_owns_the_next_step():
    app = (ROOT / "web/app.js").read_text()
    perspectives = (ROOT / "web/perspectives.js").read_text()
    css = (ROOT / "web/style.css").read_text()

    assert "function reviewRoute(" in perspectives
    assert "Agent can investigate" in perspectives
    assert "Human decision needed" in perspectives
    assert "Agent can investigate · ${agentCount}" in app
    assert "Human decision needed · ${humanCount}" in app
    assert "Ask my agent to prepare" in perspectives
    assert "Send to my agent" in perspectives
    assert 'class="review-route ${route.key}"' in app
    assert ".review-route.agent" in css
    assert ".review-route.human" in css


def test_impact_page_is_available_in_demo_and_private_workspaces():
    app = (ROOT / "web/app.js").read_text()
    html = (ROOT / "web/index.html").read_text()
    css = (ROOT / "web/style.css").read_text()

    assert 'data-view="impact"' in html
    assert "impact:'Impact'" in app
    assert "impact:impactView" in app
    assert "function impactMetrics()" in app
    assert "function monitoredSystemIds()" in app
    assert "r.status==='complete'" in app
    assert "apps:monitored.size" in app
    assert "Apps evaluated" in app
    assert "Apps needing review" in app
    assert "f.relevance==='relevant'" in app
    assert "f.relevance==='not_relevant'" in app
    assert "f.relevance==='insufficient_information'" in app
    assert "evaluations_performed" in app
    assert "review_events_created" in app
    assert "LIVE_REFRESH_MS=600000" in app
    assert "This page refreshes every 10 minutes" in app
    assert "function globalImpactPanel()" in app
    assert "/api/public-impact" in app
    assert "Impact across participating workspaces" in app
    assert "Anonymous totals from every workspace" in app
    assert "Saved demonstration" in app
    assert "Your workspace" in app
    assert ".impact-summary{display:grid" in css


def test_draft_notice_and_context_save_action_remain_visible_on_mobile():
    app = (ROOT / "web/app.js").read_text()
    css = (ROOT / "web/style.css").read_text()

    assert 'class="notice info draft-ready"' in app
    assert '.draft-ready{display:flex' in css
    assert '.draft-ready{display:grid;grid-template-columns:1fr;gap:12px}' in css
    save_action = (
        '<div class="modal-actions"><button class="button primary" '
        'type="submit">Save context</button></div>'
    )
    assert save_action in app
    assert '.modal-footer{padding-bottom:calc(28px + env(safe-area-inset-bottom))!important}' in css


def test_unchecked_profiles_are_not_described_as_monitored():
    app = (ROOT / "web/app.js").read_text()

    assert "Profile only · not evaluated" in app
    assert "Waiting for first check" in app
    assert "Profiles you add to the demo stay local and are not evaluated." in app


def test_public_demo_offers_multiple_safe_example_inputs():
    app = (ROOT / "web/app.js").read_text()
    demo = (ROOT / "web/demo.js").read_text()

    assert "const demoExampleInputs=" in app
    assert "data-demo-example" in app
    for label in ("Incident Alert Bot", "Subscription Billing Helper", "Release Notes Agent"):
        assert label in app
    assert "normalizeSystem" in demo
    assert "items.map(normalizeSystem)" in demo


def test_docs_include_interactive_architecture_map():
    app = (ROOT / "web/app.js").read_text()
    css = (ROOT / "web/style.css").read_text()

    assert "function architectureDocs()" in app
    assert "How data moves through BuiltWatch" in app
    assert "import:{eyebrow:'1 · IMPORT'" in app
    assert "outcome:{eyebrow:'5 · OUTCOME'" in app
    assert 'data-architecture="${key}"' in app
    assert "NEVER SHARED" in app
    assert "No stage starts a paid check unless you choose a live check." in app
    assert ".architecture-stage-tabs" in css
    assert "@media(max-width:600px)" in css


def test_every_registry_category_has_a_display_name_and_blurb():
    """A source in an unnamed category would render under a blank heading.

    The sources view groups by category, so adding one to sources/registry.yaml without a
    matching label in perspectives.js and a blurb in app.js silently produces an empty
    group header. Cheap to prevent, annoying to notice.
    """
    import yaml

    registry = yaml.safe_load((ROOT / "sources/registry.yaml").read_text())
    categories = {s["category"] for s in registry["sources"]}

    topics = (ROOT / "web/perspectives.js").read_text()
    app = (ROOT / "web/app.js").read_text()
    order_line = app[app.index("const CATEGORY_ORDER=") : app.index("const BLURBS=")]

    for category in sorted(categories):
        assert f"{category}:'" in topics, f"{category} has no display name in perspectives.js"
        assert f"{category}:'" in app, f"{category} has no blurb in app.js"
        assert f"'{category}'" in order_line, f"{category} is missing from CATEGORY_ORDER"


def test_sources_view_groups_by_category_and_surfaces_coverage_failures():
    """Invariant 1 must survive the grouped layout.

    A failed fetch has to remain visible. In the grouped view that means a per-group
    amber count, not only the per-row pill — otherwise a collapsed or skimmed group
    could read as an all-clear.
    """
    app = (ROOT / "web/app.js").read_text()
    start = app.index("function sourcesView(){")
    view = app[start : app.index("\nfunction ", start + 10)]

    assert "CATEGORY_ORDER" in view and "source-group" in view, "sources view is not grouped"
    assert "sourceFilter" in view and "data-source-filter" in view, "sources view has no category filter"
    assert '<details class="panel source-group"' in view, "source groups are not collapsible"
    assert "source-filter-button" in view, "source filter counts are not rendered"
    assert "could not be checked" in view, "group header does not report fetch failures"
    assert "pill amber" in view, "fetch failures are not visually distinguished"
    # The whole-registry count must stay honest about what is and is not watched.
    assert "Nothing outside this list is checked" in view


def test_demo_lists_every_registry_source():
    """The demo must advertise the same coverage the system actually watches.

    `web/demo.json` is generated from a local replay database, so adding a source to the
    registry does not update it. That drift is invisible in every other test, and it lands
    on the one page whose entire claim is that coverage is explicit and listed in full:
    an unauthenticated visitor was shown "11 sources across 7 categories" while the
    registry held 12 across 8, silently dropping the only business_news source.
    """
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from builtwatch.registry import load_registry

    demo = json.loads((ROOT / "web/demo.json").read_text())
    demo_ids = {s["id"] for s in demo["sources"]}
    registry_ids = {s.id for s in load_registry(ROOT / "sources/registry.yaml")}

    missing = registry_ids - demo_ids
    assert not missing, (
        f"sources in the registry but absent from the demo: {sorted(missing)}. "
        "Regenerate with scripts/export_demo.py, or the demo understates coverage."
    )
    assert not demo_ids - registry_ids, "demo lists a source the registry does not contain"
