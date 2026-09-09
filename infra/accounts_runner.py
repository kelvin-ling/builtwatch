"""HTTP account API and separately deployed background worker."""

from __future__ import annotations

import json
import os
import time

import boto3
from boto3.dynamodb.conditions import Key

from builtwatch.admission import admit, allow_request
from builtwatch.accounts import serve, verify, work
from builtwatch.config import Settings
from builtwatch.dynamo_store import DynamoStore
from builtwatch.pipeline import run_scan
from builtwatch.web_api import response


def lambda_handler(event, context):
    table = boto3.resource("dynamodb").Table(os.environ["BW_TABLE"])
    settings = Settings()

    def invoke(payload):
        boto3.client("lambda").invoke(
            FunctionName=os.environ["BW_WORKER"],
            InvocationType="Event",
            Payload=json.dumps(payload).encode(),
        )

    if "requestContext" in event:
        tenant = verify(event, os.environ.get("BW_PROXY_SECRET", ""), table)
        if not tenant:
            return response(401, {"error": "Please sign in to BuiltWatch."})
        if event.get("rawPath") == "/api/admin":
            if tenant != os.environ.get("BW_OWNER_ACCOUNT"):
                return response(403, {"error": "Owner access required."})
            if event["requestContext"]["http"]["method"] == "POST":
                try:
                    import base64

                    raw = event.get("body") or "{}"
                    if event.get("isBase64Encoded"):
                        raw = base64.b64decode(raw).decode()
                    paused = json.loads(raw).get("paused")
                    if not isinstance(paused, bool):
                        raise ValueError()
                    table.put_item(Item={"pk": "ADMIN", "sk": "control", "paused": paused})
                except (ValueError, TypeError, AttributeError):
                    return response(400, {"error": "Choose pause or resume."})
            elif event["requestContext"]["http"]["method"] != "GET":
                return response(405, {"error": "Method not allowed."})
            cached = table.get_item(Key={"pk": "ADMIN", "sk": "snapshot"}).get("Item", {})
            data = json.loads(cached.get("payload", "{}"))
            data["manual_paused"] = (
                table.get_item(Key={"pk": "ADMIN", "sk": "control"})
                .get("Item", {})
                .get("paused", False)
            )
            if not data.get("checked_at"):
                data["warnings"] = [
                    "Cost monitoring is being configured. Paid checks remain paused until a fresh status is available."
                ]
            return response(200, data)
        if not allow_request(table, tenant):
            return response(
                429, {"error": "Your daily request allowance is used. Please return tomorrow."}
            )
        if not admit(table, tenant):
            return response(
                403,
                {
                    "code": "pilot_full",
                    "error": "All 25 pilot workspaces are currently in use. You can still explore the sample. Please try again later.",
                },
            )
        try:
            return serve(event, DynamoStore(table, tenant), settings, invoke)
        except Exception:
            # No profile or upstream exception details leak into public error responses.
            return response(
                503, {"error": "The workspace service is temporarily unavailable. Please retry."}
            )
    if event.get("task") == "daily":
        args = {"KeyConditionExpression": Key("pk").eq("DIRECTORY")}
        count = 0
        while True:
            page = table.query(**args)
            for item in page.get("Items", []):
                store = DynamoStore(table, item["sk"])
                if (store.get("preferences") or {}).get("automatic_checks", True):
                    serve(
                        {
                            "requestContext": {"http": {"method": "POST"}},
                            "rawPath": "/api/scan",
                            "body": "{}",
                        },
                        store,
                        settings,
                        invoke,
                    )
                    count += 1
            if "LastEvaluatedKey" not in page:
                return {"workspaces": count}
            args["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    if event.get("task") == "intake":
        from builtwatch.web_intake import draft_profile

        os.environ["BW_DEADLINE"] = str(time.time() + 90)
        return draft_profile(event, DynamoStore(table, event["tenant"]), settings)
    if event.get("task") == "scan":
        os.environ["BW_DEADLINE"] = str(time.time() + 480)
        return work(event, DynamoStore(table, event["tenant"]), settings, run_scan)
    return response(400, {"error": "Unknown event"})
