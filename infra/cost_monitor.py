"""Daily cached cost guard; no per-visitor billing API calls."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key

CONFIRM_WARNING = "Confirm the AWS email subscription to receive operational warnings."


# Reported account cost at which paid checks stop entirely.
PAUSE_AT_USD = 10
# Reported account cost at which the owner is warned but checks continue.
WARN_AT_USD = 7
# Shared monthly model reserve, in USD, at which the allowance is called nearly used.
RESERVE_WARN_USD = 4


def email_confirmed(session):
    try:
        subscriptions = session.client("sns").list_subscriptions_by_topic(
            TopicArn=os.environ["BW_ALERT_TOPIC"]
        )["Subscriptions"]
        return any(
            x["Protocol"] == "email" and x["SubscriptionArn"] != "PendingConfirmation"
            for x in subscriptions
        )
    except Exception:  # noqa: BLE001 - any failure must pause checks, not crash the monitor
        return False


def lambda_handler(event, context):
    s = boto3.Session(region_name="us-east-1")
    t = s.resource("dynamodb").Table(os.environ["BW_TABLE"])
    now = datetime.now(timezone.utc)
    day = now.date().isoformat()
    month = day[:7]
    previous = t.get_item(Key={"pk": "ADMIN", "sk": "snapshot"}).get("Item", {})
    if previous.get("day") == day and not previous.get("error"):
        # Confirmation can be refreshed without another paid billing query.
        data = json.loads(previous.get("payload", "{}"))
        confirmed = email_confirmed(s)
        data["email_confirmed"] = confirmed
        if confirmed:
            data["warnings"] = [w for w in data.get("warnings", []) if w != CONFIRM_WARNING]
        elif CONFIRM_WARNING not in data.get("warnings", []):
            data.setdefault("warnings", []).append(CONFIRM_WARNING)
        data["active_workspaces"] = len(
            t.query(KeyConditionExpression=Key("pk").eq("SEATS")).get("Items", [])
        )
        previous["payload"] = json.dumps(data)
        t.put_item(Item=previous)
        return {"cached": True, "email_confirmed": confirmed}
    warnings = []
    daily = []
    total = None
    error = None
    try:
        result = s.client("ce").get_cost_and_usage(
            TimePeriod={
                "Start": month + "-01",
                "End": (now.date() + timedelta(days=1)).isoformat(),
            },
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            Filter={"Not": {"Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit", "Refund"]}}},
        )
        daily = [
            {
                "date": x["TimePeriod"]["Start"],
                "usd": max(0, float(x["Total"]["UnblendedCost"]["Amount"])),
            }
            for x in result["ResultsByTime"]
        ]
        total = sum(x["usd"] for x in daily)
    except Exception:  # noqa: BLE001 - any failure must pause checks, not crash the monitor
        error = (
            "Billing data could not be refreshed. Paid checks are paused until monitoring recovers."
        )
        warnings.append(error)
    count = None
    try:
        count = s.client("cognito-idp").describe_user_pool(UserPoolId=os.environ["BW_USER_POOL"])[
            "UserPool"
        ]["EstimatedNumberOfUsers"]
    except Exception:  # noqa: BLE001 - any failure must pause checks, not crash the monitor
        warnings.append("Registration count is temporarily unavailable.")
    accounts = t.query(KeyConditionExpression=Key("pk").eq("SEATS")).get("Items", [])
    systems = jobs = failures = 0
    for account in accounts[:25]:
        pk = "USER#" + account["sk"]
        systems += len(
            t.query(KeyConditionExpression=Key("pk").eq(pk) & Key("sk").begins_with("system#")).get(
                "Items", []
            )
        )
        job = t.get_item(Key={"pk": pk, "sk": "job"}).get("Item", {})
        if job:
            value = json.loads(job.get("payload", "{}"))
            jobs += 1
            failures += int(value.get("status") in ("failed", "aborted", "paused"))
    allocated = float(
        t.get_item(Key={"pk": "BUDGET", "sk": month}).get("Item", {}).get("allocated", 0)
    )
    paused = total is None or total >= PAUSE_AT_USD
    completed = daily[:-1]
    if completed:
        baseline = sum(x["usd"] for x in completed[-4:-1]) / max(1, len(completed[-4:-1]))
        if completed[-1]["usd"] >= 1 and completed[-1]["usd"] > max(1, baseline * 3):
            warnings.append(
                "Unusual spend: the last completed day exceeded USD 1 "
                "and three times its recent baseline."
            )
    if total is not None and total >= WARN_AT_USD:
        warnings.append(
            "Approaching the operating allowance. Review the service breakdown in AWS Billing."
        )
    if paused:
        warnings.append(
            "Paid checks are paused conservatively. "
            "Saved workspaces and the local demo remain available."
        )
    if allocated >= RESERVE_WARN_USD:
        warnings.append("The shared USD 5 monthly model reserve is nearly used.")
    confirmed = email_confirmed(s)
    if not confirmed:
        warnings.append(CONFIRM_WARNING)
    data = {
        "checked_at": int(time.time()),
        "day": day,
        "month": month,
        "paused": paused,
        "error": error,
        "actual_usd": total,
        "actual_cad_buffered": round(total * 1.5, 2) if total is not None else None,
        "monthly_target_cad": 25,
        "stop_usd": 10,
        "cad_per_usd_buffer": 1.5,
        "daily": daily,
        "registered_accounts": count,
        "active_workspaces": len(accounts),
        "systems": systems,
        "workspaces_with_jobs": jobs,
        "jobs_needing_attention": failures,
        "model_allocated_usd": allocated,
        "model_limit_usd": 5,
        "warnings": warnings,
        "email_confirmed": confirmed,
        "scope": (
            "Whole AWS account before credits/refunds; may include other projects. "
            "Billing is delayed. CAD uses a conservative planning rate, not a live FX quote."
        ),
    }
    t.put_item(
        Item={
            "pk": "ADMIN",
            "sk": "snapshot",
            "paused": paused,
            "checked_at": int(time.time()),
            "day": day,
            "error": error,
            "payload": json.dumps(data),
        }
    )
    if warnings and confirmed:
        key = {"pk": "ADMIN", "sk": "alert-" + day}
        if "Item" not in t.get_item(Key=key):
            s.client("sns").publish(
                TopicArn=os.environ["BW_ALERT_TOPIC"],
                Subject="BuiltWatch cost and service warning",
                Message="\n".join(warnings)
                + (
                    "\n\nMonthly target: CAD 25. Paid checks pause at USD 10 reported "
                    "account cost, with USD 5 shared model reservations. Billing can lag; "
                    "this is not an exact invoice cap."
                    "\nhttps://builtwatch.org/#admin"
                ),
            )
            t.put_item(Item={**key, "expires": int(time.time()) + 2678400})
    return {"updated": True, "paused": paused, "email_confirmed": confirmed}
