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


def test_completed_checks_do_not_create_a_global_status_banner():
    app = (ROOT / "web/app.js").read_text()
    notice = app[app.index("function jobNotice()") : app.index("function render()")]

    assert "state.job.status!=='idle'" not in app
    assert "function jobNotice()" in app
    assert "complete:'" not in notice


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
    assert "could not be checked" in view, "group header does not report fetch failures"
    assert "pill amber" in view, "fetch failures are not visually distinguished"
    # The whole-registry count must stay honest about what is and is not watched.
    assert "Nothing outside this list is checked" in view
