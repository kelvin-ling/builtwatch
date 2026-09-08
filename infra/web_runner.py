"""Single-owner Lambda, persistent SQLite checkpoints in private S3.

Deployment MUST reserve concurrency=1. Every invocation downloads the latest checkpoint,
closes SQLite before upload, and never uses a warm /tmp database as authoritative state.
The public function URL exposes only token-authenticated API operations. Scheduled events
arrive through IAM and use the same serialized function.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from builtwatch.config import Settings
from builtwatch.pipeline import run_scan
from builtwatch.store import Store
from builtwatch.web_api import authorized, dispatch, response


def lambda_handler(event, context):
    is_http = "requestContext" in event
    if is_http and not authorized(event):
        return response(401, {"error": "Connect with your workspace access key."})
    settings = Settings()
    bucket = os.environ["BW_STATE_BUCKET"]
    s3 = boto3.client("s3")
    with tempfile.TemporaryDirectory() as folder:
        db = Path(folder) / "state.db"
        try:
            s3.download_file(bucket, "workspace.db", str(db))
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in {"404", "NoSuchKey"}:
                raise
        store = Store(db)
        queued = []
        try:
            if is_http:
                result = dispatch(event, store, settings, lambda: queued.append(True))
            elif event.get("task") == "scan":
                os.environ["BW_DEADLINE"] = str(time.time() + 480)
                run = run_scan(store, settings, mode="live")
                result = response(200, {"status": run.run.status, "summary": run.summary_line()})
            else:
                result = response(400, {"error": "Unknown event"})
        finally:
            store.close()
            # Persist even an aborted scan: budget and partial progress must survive.
            s3.upload_file(
                str(db), bucket, "workspace.db", ExtraArgs={"ServerSideEncryption": "AES256"}
            )
        if queued:
            boto3.client("lambda").invoke(
                FunctionName=context.function_name,
                InvocationType="Event",
                Payload=b'{"task":"scan"}',
            )
        return result
