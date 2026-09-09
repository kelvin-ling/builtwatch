"""Bound pilot enrollment independently of authentication and model spending."""

from __future__ import annotations

import time
import uuid
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

MAX_WORKSPACES = 25
DAILY_REQUESTS = 300


def admitted(table: Any, tenant: str) -> bool:
    return bool(table.get_item(Key={"pk": "SEATS", "sk": tenant}, ConsistentRead=True).get("Item"))


def admit(table: Any, tenant: str) -> bool:
    if admitted(table, tenant):
        return True
    nonce = str(uuid.uuid4())
    try:
        table.put_item(
            Item={
                "pk": "CONTROL",
                "sk": "enrollment-lock",
                "nonce": nonce,
                "expires": int(time.time()) + 10,
            },
            ConditionExpression="attribute_not_exists(pk) OR expires < :now",
            ExpressionAttributeValues={":now": int(time.time())},
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
    try:
        # At most MAX_WORKSPACES small items; a locked consistent query bounds enrollment.
        seats = table.query(KeyConditionExpression=Key("pk").eq("SEATS"), ConsistentRead=True)[
            "Items"
        ]
        if any(item["sk"] == tenant for item in seats):
            return True
        if len(seats) >= MAX_WORKSPACES:
            return False
        table.put_item(Item={"pk": "SEATS", "sk": tenant})
        return True
    finally:
        table.delete_item(
            Key={"pk": "CONTROL", "sk": "enrollment-lock"},
            ConditionExpression="nonce = :n",
            ExpressionAttributeValues={":n": nonce},
        )


def allow_request(
    table: Any, tenant: str, limit: int = DAILY_REQUESTS, bucket: str = "requests"
) -> bool:
    day = time.strftime("%Y-%m-%d", time.gmtime())
    try:
        table.update_item(
            Key={"pk": "LIMIT#" + tenant, "sk": bucket + "#" + day},
            UpdateExpression="SET expires = :expiry ADD used :one",
            ConditionExpression="attribute_not_exists(used) OR used < :limit",
            ExpressionAttributeValues={
                ":expiry": int(time.time()) + 172800,
                ":one": 1,
                ":limit": limit,
            },
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
