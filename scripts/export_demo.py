"""Export only the checked-in example systems from an actual local replay run."""
from __future__ import annotations

import json
import os
from pathlib import Path

from builtwatch.config import Settings
from builtwatch.store import Store
from builtwatch.web_api import workspace

root = Path(__file__).resolve().parents[1]
store = Store(root / os.environ.get("BW_DEMO_DB", "data/builtwatch2.db"))
data = workspace(store, Settings())
allowed = {p.stem for p in (root / "examples/passports").glob("*.json")}
data["systems"] = [s for s in data["systems"] if s["id"] in allowed]
# Keep the public walkthrough useful even after a quality-rule release supersedes
# older findings in the private workspace.  The demo is explicitly historical, so
# it may show the last grounded replay while the signed-in workspace starts clean.
if not data["findings"]:
    historical = []
    for finding in store.list_findings(current_only=False, limit=300):
        if finding.system_id not in allowed:
            continue
        item = finding.model_dump(mode="json")
        decisions = [d for d in store.dispositions_for(finding.id) if d.action.value != "exported"]
        item["disposition"] = decisions[-1].action.value if decisions else "open"
        historical.append(item)
    data["findings"] = historical
else:
    data["findings"] = [f for f in data["findings"] if f["system_id"] in allowed]

# No text is rewritten here. demo.json is presented as saved results from a real replay,
# and evidence passages are verbatim quotes checked against stored snapshots; rewriting
# either breaks that claim. Provider neutrality belongs in the example passports, which
# are inputs, not in the model's output. (An earlier string scrub produced "the the
# model" and "a Bedrock model and a Bedrock model" on the public demo.)
runs = store.list_runs(limit=1)
replay_day = runs[0].started_at.strftime("%-d %B %Y") if runs else "an earlier date"
data["replay_date"] = replay_day
data["demo"] = True
data["demo_note"] = (
    f"Saved results from a real source replay run on {replay_day}. "
    "Historical material; not a live change alert."
)
(root / "web/demo.json").write_text(json.dumps(data, indent=2))
store.close()
