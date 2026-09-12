"""Provision the AWS-side spend backstop.

Creates a monthly cost budget with email alerts. This is a backstop, not the primary
control — the in-app ceilings in builtwatch/config.py abort a run *before* spending.
AWS Budgets alert after the fact.

    python infra/budget.py --email you@example.com --limit 20

Budgets are free for the first two per account.
"""

from __future__ import annotations

import argparse

import boto3
from botocore.exceptions import ClientError

BUDGET_NAME = "builtwatch-monthly-20usd"
THRESHOLDS = [(50.0, "ACTUAL"), (80.0, "ACTUAL"), (100.0, "ACTUAL"), (100.0, "FORECASTED")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Where alerts are sent.")
    parser.add_argument("--limit", default="5", help="Monthly USD alert ceiling.")
    parser.add_argument("--name", default=BUDGET_NAME)
    args = parser.parse_args()

    account_id = boto3.client("sts").get_caller_identity()["Account"]
    budgets = boto3.client("budgets", region_name="us-east-1")

    subscribers = [{"SubscriptionType": "EMAIL", "Address": args.email}]
    notifications = [
        {
            "Notification": {
                "NotificationType": kind,
                "ComparisonOperator": "GREATER_THAN",
                "Threshold": threshold,
                "ThresholdType": "PERCENTAGE",
            },
            "Subscribers": subscribers,
        }
        for threshold, kind in THRESHOLDS
    ]

    try:
        budgets.create_budget(
            AccountId=account_id,
            Budget={
                "BudgetName": args.name,
                "BudgetLimit": {"Amount": str(args.limit), "Unit": "USD"},
                "TimeUnit": "MONTHLY",
                "BudgetType": "COST",
            },
            NotificationsWithSubscribers=notifications,
        )
        print(f"created budget {args.name} (${args.limit}/month) on account {account_id}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "DuplicateRecordException":
            print(f"budget {args.name} already exists — not modified")
        else:
            raise

    described = budgets.describe_budget(AccountId=account_id, BudgetName=args.name)["Budget"]
    spend = described.get("CalculatedSpend", {}).get("ActualSpend", {})
    print(f"limit: {described['BudgetLimit']['Amount']} USD | actual: {spend.get('Amount', '0')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
