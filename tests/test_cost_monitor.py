from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import boto3
from moto import mock_aws


def test_daily_monitor_pauses_and_caches_without_requerying_billing(monkeypatch):
    spec = importlib.util.spec_from_file_location("cost_monitor", Path("infra/cost_monitor.py"))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    monkeypatch.setenv("BW_TABLE", "cost-test")
    monkeypatch.setenv("BW_USER_POOL", "test-pool")
    monkeypatch.setenv("BW_ALERT_TOPIC", "test-topic")
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        table = resource.create_table(
            TableName="cost-test",
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[{"AttributeName": x, "AttributeType": "S"} for x in ("pk", "sk")],
        )
        calls = []
        confirmed = [False]

        def cost(**kwargs):
            calls.append("billing")
            return {
                "ResultsByTime": [
                    {
                        "TimePeriod": {"Start": "2026-09-01"},
                        "Total": {"UnblendedCost": {"Amount": "11"}},
                    }
                ]
            }

        clients = {
            "ce": SimpleNamespace(get_cost_and_usage=cost),
            "cognito-idp": SimpleNamespace(
                describe_user_pool=lambda **kw: {"UserPool": {"EstimatedNumberOfUsers": 3}}
            ),
            "sns": SimpleNamespace(
                list_subscriptions_by_topic=lambda **kw: {
                    "Subscriptions": [
                        {
                            "Protocol": "email",
                            "SubscriptionArn": "confirmed"
                            if confirmed[0]
                            else "PendingConfirmation",
                        }
                    ]
                },
                publish=lambda **kw: calls.append("email"),
            ),
        }
        monkeypatch.setattr(
            monitor.boto3,
            "Session",
            lambda **kw: SimpleNamespace(
                resource=lambda service: resource, client=lambda name: clients[name]
            ),
        )
        table.put_item(Item={"pk": "SEATS", "sk": "real"})
        table.put_item(Item={"pk": "DIRECTORY", "sk": "old-test"})
        result = monitor.lambda_handler({}, None)
        assert result["paused"] and not result["email_confirmed"]
        payload = json.loads(
            table.get_item(Key={"pk": "ADMIN", "sk": "snapshot"})["Item"]["payload"]
        )
        assert payload["active_workspaces"] == 1
        assert payload["registered_accounts"] == 3
        confirmed[0] = True
        assert monitor.lambda_handler({}, None)["email_confirmed"]
        assert calls == ["billing"]
        payload = json.loads(
            table.get_item(Key={"pk": "ADMIN", "sk": "snapshot"})["Item"]["payload"]
        )
        assert monitor.CONFIRM_WARNING not in payload["warnings"]
        assert payload["paused"]
