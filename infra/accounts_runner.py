"""HTTP account API and separately deployed background worker."""

from __future__ import annotations

import json
import os
import time

import boto3
from boto3.dynamodb.conditions import Key

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
    if event.get("task") == "scan":
        os.environ["BW_DEADLINE"] = str(time.time() + 480)
        return work(event, DynamoStore(table, event["tenant"]), settings, run_scan)
    return response(400, {"error": "Unknown event"})
