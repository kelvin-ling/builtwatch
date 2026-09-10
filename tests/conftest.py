from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from builtwatch.models import (
    ConsequentialAction,
    Evidence,
    FetchStatus,
    Finding,
    Relevance,
    Source,
    SourceCategory,
    SourceSnapshot,
    SystemFactRef,
    SystemPassport,
)
from builtwatch.quality import QUALITY_VERSION
from builtwatch.store import Store

SNAPSHOT_TEXT = (
    "From 1 February 2026, bulk senders must authenticate outgoing mail with SPF and "
    "DKIM, publish a DMARC policy, and offer one-click unsubscribe in all commercial "
    "messages. Senders exceeding a spam rate of 0.3% may have messages rejected."
)


@pytest.fixture(params=["sqlite", "dynamo"])
def store(tmp_path, request):
    if request.param == "sqlite":
        s = Store(tmp_path / "test.db")
        yield s
        s.close()
    else:
        import boto3
        from moto import mock_aws

        from builtwatch.dynamo_store import DynamoStore, tenant_id

        with mock_aws():
            table = boto3.resource("dynamodb", region_name="us-east-1").create_table(
                TableName="pipeline-test",
                BillingMode="PAY_PER_REQUEST",
                KeySchema=[
                    {"AttributeName": "pk", "KeyType": "HASH"},
                    {"AttributeName": "sk", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": x, "AttributeType": "S"} for x in ["pk", "sk"]
                ],
            )
            yield DynamoStore(table, tenant_id("pipeline-test-user"))


@pytest.fixture
def passport() -> SystemPassport:
    return SystemPassport(
        id="inbox-triage",
        name="Client Inbox Triage Bot",
        purpose="Drafts and sends client email replies.",
        technologies=["Python 3.12"],
        services=["Gmail API", "SendGrid"],
        consequential_actions=[
            ConsequentialAction(description="Sends email to external clients", reversible=False)
        ],
        data_categories=["email address"],
        jurisdictions=["United Kingdom"],
    )


@pytest.fixture
def source() -> Source:
    return Source(
        id="gmail-sender-guidelines",
        name="Gmail Email Sender Guidelines",
        category=SourceCategory.COMMUNICATIONS,
        url="https://support.google.com/mail/answer/81126",
        publisher="Google",
    )


@pytest.fixture
def snapshot() -> SourceSnapshot:
    snap = SourceSnapshot(
        id="snap_test01",
        source_id="gmail-sender-guidelines",
        mode="replay",
        content=SNAPSHOT_TEXT,
        published_at=date(2026, 1, 15),
        retrieved_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        fetch_status=FetchStatus.OK,
    )
    snap.content_hash = snap.compute_hash()
    return snap


def make_finding(
    passport: SystemPassport,
    snapshot: SourceSnapshot,
    *,
    relevance: Relevance = Relevance.RELEVANT,
    passage: str | None = None,
    fact_key: str = "services[0]",
    fact_value: str = "Gmail API",
    development_key: str = "gmail-bulk-sender-2026",
    facts: list[str] | None = None,
    finding_id: str = "find_test01",
) -> Finding:
    f = Finding(
        quality_version=QUALITY_VERSION,
        id=finding_id,
        scan_run_id="run_test01",
        system_id=passport.id,
        source_id=snapshot.source_id,
        relevance=relevance,
        title="Gmail bulk sender requirements",
        development_key=development_key,
        evidence=[
            Evidence(
                snapshot_id=snapshot.id,
                source_id=snapshot.source_id,
                passage=passage or SNAPSHOT_TEXT[:160],
                published_at=snapshot.published_at,
            )
        ],
        system_facts=[SystemFactRef(key=fact_key, value=fact_value)],
        facts=facts or ["Bulk senders must publish a DMARC policy."],
    )
    f.revision_hash = f.compute_revision_hash()
    return f
