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
