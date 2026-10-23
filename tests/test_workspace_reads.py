"""The workspace read is the hot path: every page load and refresh makes it."""

from __future__ import annotations

import json

from conftest import make_finding

from builtwatch.accounts import serve
from builtwatch.config import Settings
from builtwatch.dynamo_store import DynamoStore, tenant_id
from builtwatch.models import Disposition, DispositionAction


def _count_calls(table, names):
    calls = {name: 0 for name in names}
    for name in names:
        original = getattr(table, name)

        def counted(*args, _name=name, _original=original, **kwargs):
            calls[_name] += 1
            return _original(*args, **kwargs)

        setattr(table, name, counted)
    return calls


def _workspace(store):
    event = {"rawPath": "/api/workspace", "requestContext": {"http": {"method": "GET"}}}
    result = serve(event, store, Settings(), None)
    assert result["statusCode"] == 200
    return json.loads(result["body"])


def test_workspace_reads_do_not_grow_with_findings_or_apps(table, passport, snapshot):
    store = DynamoStore(table, tenant_id("alice"))
    apps = [passport.model_copy(update={"id": f"app-{n}", "name": f"App {n}"}) for n in range(4)]
    for app in apps:
        store.upsert_system(app)
    for n in range(24):
        finding, _ = store.save_finding(
            make_finding(
                apps[n % 4],
                snapshot,
                finding_id=f"find_{n:02d}",
                development_key=f"development-{n}",
            )
        )
        if n % 3 == 0:
            store.add_disposition(
                Disposition(id=f"disp_{n:02d}", finding_id=finding.id, action="acknowledged")
            )
    store.add_disposition(
        Disposition(id="disp_zz", finding_id="find_03", action=DispositionAction.EXPORTED)
    )
    store.put("agent-review#app-1", {"system_id": "app-1", "finding_id": "find_01"})

    calls = _count_calls(table, ["query", "get_item"])
    data = _workspace(store)

    by_id = {f["id"]: f["disposition"] for f in data["findings"]}
    assert len(by_id) == 24
    assert by_id["find_00"] == "acknowledged"
    assert by_id["find_03"] == "acknowledged"  # an export is not a decision
    assert by_id["find_01"] == "open"
    assert [r["system_id"] for r in data["agent_reviews"]] == ["app-1"]
    # One query per record family and one read per workspace setting, whatever the size.
    assert calls["query"] <= 6, calls
    assert calls["get_item"] <= 4, calls



def test_product_names_are_resolved_once_per_workspace_read(table, passport, snapshot):
    from builtwatch.rules import dependency_aliases

    store = DynamoStore(table, tenant_id("alice"))
    store.upsert_system(passport)
    for n in range(30):
        finding = make_finding(
            passport, snapshot, finding_id=f"find_{n:02d}", development_key=f"dev-{n}"
        )
        finding.assessment_method = "rules-v2"
        store.save_finding(finding)
    dependency_aliases.cache_clear()

    assert len(_workspace(store)["findings"]) == 30
    # One lookup per declared product (Python, Gmail API, SendGrid), not one per review.
    assert dependency_aliases.cache_info().misses <= 3

def test_repeating_an_outcome_records_it_once(table, passport, snapshot):
    from builtwatch.accounts import public_impact

    store = DynamoStore(table, tenant_id("alice"))
    store.upsert_system(passport)
    store.register()
    finding, _ = store.save_finding(make_finding(passport, snapshot))

    def record(action, reason="Reviewed; no app change needed."):
        body = json.dumps({"finding_id": finding.id, "action": action, "reason": reason})
        event = {
            "rawPath": "/api/dispositions",
            "requestContext": {"http": {"method": "POST"}},
            "body": body,
        }
        result = serve(event, store, Settings(), None)
        assert result["statusCode"] == 200

    # A retry after a timed-out response must not count as a second decision.
    record("acknowledged")
    record("acknowledged")
    assert len(store.dispositions_for(finding.id)) == 1
    assert public_impact(table, Settings())["outcomes_recorded"] == 1
    # A changed decision is still recorded.
    record("dismissed", "We no longer use this service.")
    assert [d.action.value for d in store.dispositions_for(finding.id)] == [
        "acknowledged",
        "dismissed",
    ]


def test_rejected_agent_sync_saves_nothing(table):
    from builtwatch.models import SystemPassport

    store = DynamoStore(table, tenant_id("agent-owner"))
    profile = SystemPassport(id="agent-12345678-123", name="Connected", purpose="Draft replies")
    body = {
        "system_id": profile.id,
        "profile": profile.model_dump(mode="json"),
        "review": {
            "finding_id": "find-missing",
            "outcome": "no_change_needed",
            "summary": "The project does not use the affected feature.",
        },
    }
    event = {
        "rawPath": "/api/agent/sync",
        "requestContext": {"http": {"method": "POST"}},
        "body": json.dumps(body),
    }
    result = serve(event, store, Settings(), None)
    # The agent is told the request failed, so none of it may have been applied.
    assert result["statusCode"] == 400
    assert store.get_system(profile.id) is None
