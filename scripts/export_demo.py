"""Export only the checked-in example systems from an actual local replay run."""
from __future__ import annotations

import json
from pathlib import Path

from builtwatch.config import Settings
from builtwatch.store import Store
from builtwatch.web_api import workspace

root = Path(__file__).resolve().parents[1]
store = Store(root / "data/builtwatch2.db")
data = workspace(store, Settings())
allowed = {p.stem for p in (root / "examples/passports").glob("*.json")}
data["systems"] = [s for s in data["systems"] if s["id"] in allowed]
data["findings"] = [f for f in data["findings"] if f["system_id"] in allowed]
data["demo"] = True
data["demo_note"] = "Saved results from a real Strands + Amazon Nova replay on 8 September 2026. Historical material; not a live change alert."
(root / "web/demo.json").write_text(json.dumps(data, indent=2))
store.close()
