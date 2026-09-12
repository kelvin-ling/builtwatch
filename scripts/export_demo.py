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

# Keep the unauthenticated demo provider-neutral.  The product does not require
# users to disclose which model their agent uses, and the demo should not imply a
# ChatGPT/Claude account dependency.
def scrub(value):
    if isinstance(value, str):
        replacements = (
            ("Anthropic Claude model via Amazon Bedrock", "the model via Amazon Bedrock"),
            ("Anthropic Claude via Amazon Bedrock", "the model via Amazon Bedrock"),
            ("Claude Fable 5.1", "a Bedrock model"),
            ("Claude Mythos 5.1", "a Bedrock model"),
            ("Claude Sonnet 5", "the Bedrock model"),
            ("Anthropic Messages API", "Messages API"),
            ("Claude", "the Bedrock model"),
        )
        for old, new in replacements:
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, dict):
        return {key: scrub(item) for key, item in value.items()}
    return value

data = scrub(data)
data["demo"] = True
data["demo_note"] = "Saved results from a real source replay. Historical material; not a live change alert."
(root / "web/demo.json").write_text(json.dumps(data, indent=2))
store.close()
