"""Deploy the inexpensive, single-owner web workspace. Public UI is hosted by Sites.

No always-on compute. One concurrent Lambda serializes S3/SQLite checkpoints. This is
intentionally a small personal workspace, not a multi-tenant database architecture.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import secrets
import time
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from deploy_lambda import build_zip

ROOT = Path(__file__).resolve().parents[1]
NAME = "builtwatch-workspace"
REGION = "us-east-1"
ORIGIN = "https://builtwatch.org"


def package() -> bytes:
    data = io.BytesIO(build_zip())
    with zipfile.ZipFile(data, "a", zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / "infra/web_runner.py", "web_runner.py")
    return data.getvalue()


def role(iam, name: str, service: str, policy: dict) -> str:
    try:
        arn = iam.create_role(
            RoleName=name,
            AssumeRolePolicyDocument=json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": service},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                }
            ),
        )["Role"]["Arn"]
        time.sleep(10)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "EntityAlreadyExists":
            raise
        arn = iam.get_role(RoleName=name)["Role"]["Arn"]
    iam.put_role_policy(
        RoleName=name, PolicyName="builtwatch-access", PolicyDocument=json.dumps(policy)
    )
    return arn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()
    archive = ROOT / "data/workspace.zip"
    archive.parent.mkdir(exist_ok=True)
    if args.build_only or not archive.exists():
        archive.write_bytes(package())
    if args.build_only:
        return
    session = boto3.Session(region_name=REGION)
    account = session.client("sts").get_caller_identity()["Account"]
    if account != "[aws-account-redacted]":
        raise RuntimeError("Wrong AWS account; use [aws-profile-redacted]")
    bucket = f"builtwatch-workspace-{account}"
    s3, lam, iam = (session.client(x) for x in ("s3", "lambda", "iam"))
    try:
        s3.create_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
            raise
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    s3.put_bucket_encryption(
        Bucket=bucket,
        ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        },
    )
    s3.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})
    s3.put_bucket_lifecycle_configuration(
        Bucket=bucket,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "short-history",
                    "Status": "Enabled",
                    "Filter": {"Prefix": ""},
                    "NoncurrentVersionExpiration": {"NoncurrentDays": 7},
                }
            ]
        },
    )
    try:
        s3.head_object(Bucket=bucket, Key="workspace.db")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "404":
            raise
        from builtwatch.store import Store

        initial = ROOT / "data/initial-workspace.db"
        initial.unlink(missing_ok=True)
        Store(initial).close()
        s3.upload_file(str(initial), bucket, "workspace.db")
    fn_arn = f"arn:aws:lambda:{REGION}:{account}:function:{NAME}"
    statements = [
        {
            "Effect": "Allow",
            "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
            "Resource": f"arn:aws:logs:{REGION}:{account}:log-group:/aws/lambda/{NAME}:*",
        },
        {
            "Effect": "Allow",
            "Action": ["s3:GetObject", "s3:PutObject"],
            "Resource": f"arn:aws:s3:::{bucket}/workspace.db",
        },
        {"Effect": "Allow", "Action": "lambda:InvokeFunction", "Resource": fn_arn},
        {
            "Effect": "Allow",
            "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            "Resource": [
                f"arn:aws:bedrock:{REGION}:{account}:inference-profile/us.amazon.nova-{m}-v1:0"
                for m in ("lite", "pro")
            ]
            + [
                f"arn:aws:bedrock:*::foundation-model/amazon.nova-{m}-v1:0" for m in ("lite", "pro")
            ],
        },
    ]
    arn = role(
        iam,
        NAME + "-role",
        "lambda.amazonaws.com",
        {"Version": "2012-10-17", "Statement": statements},
    )
    access_path = ROOT / "data/workspace-access.json"
    if access_path.exists():
        token = json.loads(access_path.read_text())["token"]
    else:
        token = secrets.token_urlsafe(36)
    env = {
        "Variables": {
            "BW_STATE_BUCKET": bucket,
            "BW_OWNER_TOKEN": token,
            "BW_SCREEN_MODEL": "us.amazon.nova-lite-v1:0",
            "BW_ASSESS_MODEL": "us.amazon.nova-pro-v1:0",
            "BW_MAX_RUN_USD": "0.25",
            "BW_MAX_DAY_USD": "0.50",
            "BW_MAX_MONTH_USD": "10.00",
            "BW_MAX_SYSTEMS": "10",
            "BW_MAX_ITERATIONS": "8",
            "BW_REGISTRY": "sources/registry.yaml",
            "BW_REPLAY": "replay",
        }
    }
    logs = session.client("logs")
    with contextlib.suppress(logs.exceptions.ResourceAlreadyExistsException):
        logs.create_log_group(logGroupName=f"/aws/lambda/{NAME}")
    logs.put_retention_policy(logGroupName=f"/aws/lambda/{NAME}", retentionInDays=7)
    try:
        lam.create_function(
            FunctionName=NAME,
            Runtime="python3.12",
            Role=arn,
            Handler="web_runner.lambda_handler",
            Code={"ZipFile": archive.read_bytes()},
            Timeout=600,
            MemorySize=512,
            Architectures=["arm64"],
            Environment=env,
        )
        lam.get_waiter("function_active_v2").wait(FunctionName=NAME)
    except lam.exceptions.ResourceConflictException:
        lam.update_function_code(FunctionName=NAME, ZipFile=archive.read_bytes())
        lam.get_waiter("function_updated_v2").wait(FunctionName=NAME)
        lam.update_function_configuration(
            FunctionName=NAME,
            Handler="web_runner.lambda_handler",
            Environment=env,
            Timeout=600,
            MemorySize=512,
        )
        lam.get_waiter("function_updated_v2").wait(FunctionName=NAME)
    # Refuse to expose endpoints until this serialization guarantee is enforced.
    lam.put_function_concurrency(FunctionName=NAME, ReservedConcurrentExecutions=1)
    cors = {
        "AllowOrigins": [ORIGIN, "http://localhost:4173"],
        "AllowMethods": ["GET", "POST", "DELETE"],
        "AllowHeaders": ["authorization", "content-type"],
        "MaxAge": 3600,
    }
    try:
        url = lam.create_function_url_config(FunctionName=NAME, AuthType="NONE", Cors=cors)[
            "FunctionUrl"
        ]
    except lam.exceptions.ResourceConflictException:
        url = lam.update_function_url_config(FunctionName=NAME, AuthType="NONE", Cors=cors)[
            "FunctionUrl"
        ]
    for sid, action, extra in [
        ("web-url", "lambda:InvokeFunctionUrl", {"FunctionUrlAuthType": "NONE"}),
        ("web-url-invoke", "lambda:InvokeFunction", {"InvokedViaFunctionUrl": True}),
    ]:
        with contextlib.suppress(lam.exceptions.ResourceConflictException):
            lam.add_permission(
                FunctionName=NAME, StatementId=sid, Action=action, Principal="*", **extra
            )
    lam.put_function_event_invoke_config(
        FunctionName=NAME, MaximumRetryAttempts=0, MaximumEventAgeInSeconds=3600
    )
    schedule_role = role(
        iam,
        NAME + "-scheduler",
        "scheduler.amazonaws.com",
        {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": "lambda:InvokeFunction", "Resource": fn_arn}
            ],
        },
    )
    scheduler = session.client("scheduler")
    config = {
        "Name": NAME + "-daily",
        "ScheduleExpression": "cron(0 7 * * ? *)",
        "ScheduleExpressionTimezone": "America/Toronto",
        "State": "ENABLED",
        "FlexibleTimeWindow": {"Mode": "OFF"},
        "Target": {
            "Arn": fn_arn,
            "RoleArn": schedule_role,
            "Input": '{"task":"scan"}',
            "RetryPolicy": {"MaximumRetryAttempts": 0, "MaximumEventAgeInSeconds": 3600},
        },
    }
    try:
        scheduler.create_schedule(**config)
    except scheduler.exceptions.ConflictException:
        scheduler.update_schedule(**config)
    access_path.write_text(json.dumps({"url": url, "token": token}))
    os.chmod(access_path, 0o600)
    instructions = ROOT / "data/WORKSPACE_ACCESS.md"
    instructions.write_text(
        f"# BuiltWatch private workspace\n\nOpen {ORIGIN}\n\n"
        f"Choose **Open your workspace** and paste this access key:\n\n`{token}`\n\n"
        "Keep this file private. The key is stored only for your browser session.\n"
        "Daily checks run at 7 a.m. Toronto time. "
        "Model threshold: $10/month, $0.50/day, $0.25/run.\n"
        "AWS hosting charges are separate. The sample workspace is public and read-only.\n"
    )
    os.chmod(instructions, 0o600)
    (ROOT / "web/config.js").write_text(f"window.BUILTWATCH_API = {json.dumps(url)};\n")
    print(f"Workspace deployed: {url}")
    print("Access instructions saved privately in data/WORKSPACE_ACCESS.md")


if __name__ == "__main__":
    main()
