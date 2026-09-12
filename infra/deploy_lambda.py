"""Deploy the watch pipeline as a scheduled Lambda.

Chosen over a container runtime for one reason: cost at rest. A Lambda behind
EventBridge Scheduler costs nothing between invocations, and a nightly watch pass at
this scale sits inside the free tier indefinitely.

    python infra/deploy_lambda.py --schedule "cron(0 7 * * ? *)"

Creates or updates: an execution role scoped to exactly the actions the pipeline needs,
a function built from a zip of this repo plus its dependencies, and a schedule. Every
resource is named builtwatch-* and can be removed with --destroy.

This is deliberately a script rather than CloudFormation: it is auditable in one read,
has no state file to drift, and the IAM policy it attaches is visible inline below
instead of hidden in a managed policy.
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
FUNCTION_NAME = "builtwatch-watch"
ROLE_NAME = "builtwatch-lambda-role"
SCHEDULE_NAME = "builtwatch-nightly"
RUNTIME = "python3.12"

TRUST_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
}

SCHEDULER_TRUST = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "scheduler.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }
    ],
}


def inline_policy(region: str, account: str) -> dict:
    """Least privilege, written out so it can be read rather than trusted.

    Note what is absent: no wildcard resource on Bedrock, no IAM, no S3, no ability to
    create anything. The pipeline only ever invokes two specific models and writes logs.
    """
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "Logs",
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                "Resource": f"arn:aws:logs:{region}:{account}:log-group:/aws/lambda/"
                f"{FUNCTION_NAME}*",
            },
            {
                "Sid": "InvokeTheTwoModelsWeActuallyUse",
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                "Resource": [
                    f"arn:aws:bedrock:{region}:{account}:inference-profile/us.amazon.nova-lite-v1:0",
                    f"arn:aws:bedrock:{region}:{account}:inference-profile/us.amazon.nova-pro-v1:0",
                    "arn:aws:bedrock:*::foundation-model/amazon.nova-lite-v1:0",
                    "arn:aws:bedrock:*::foundation-model/amazon.nova-pro-v1:0",
                ],
            },
        ],
    }


def build_zip() -> bytes:
    """Package src/, the registry, the replay corpus and dependencies into a zip."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "pkg"
        target.mkdir()
        print("installing dependencies for linux/arm64...")
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--target",
                str(target),
                "--python-platform",
                "aarch64-manylinux2014",
                "--python-version",
                "3.12",
                "--only-binary=:all:",
                "strands-agents",
                "pydantic",
                "httpx",
                "PyYAML",
                "selectolax",
            ],
            check=True,
            capture_output=True,
        )
        for item in ("src/builtwatch", "sources", "replay"):
            src = ROOT / item
            dest = target / (Path(item).name if item.startswith("src/") else item)
            subprocess.run(["cp", "-R", str(src), str(dest)], check=True)
        subprocess.run(
            ["cp", str(ROOT / "infra" / "runner.py"), str(target / "runner.py")], check=True
        )

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in target.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    zf.write(path, path.relative_to(target))
        data = buf.getvalue()
        print(f"package: {len(data) / 1_000_000:.1f} MB")
        return data


def ensure_role(iam, name: str, trust: dict, region: str, account: str) -> str:
    try:
        arn = iam.create_role(
            RoleName=name,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="BuiltWatch scheduled watch pipeline",
        )["Role"]["Arn"]
        print(f"created role {name}")
        time.sleep(10)  # IAM propagation
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "EntityAlreadyExists":
            raise
        arn = iam.get_role(RoleName=name)["Role"]["Arn"]
        print(f"role {name} already exists")

    if name == ROLE_NAME:
        iam.put_role_policy(
            RoleName=name,
            PolicyName="builtwatch-inline",
            PolicyDocument=json.dumps(inline_policy(region, account)),
        )
    return arn


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", default="cron(0 7 * * ? *)", help="EventBridge cron.")
    parser.add_argument("--mode", default="live", choices=["live", "replay"])
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--destroy", action="store_true")
    args = parser.parse_args()

    session = boto3.Session(region_name=args.region)
    account = session.client("sts").get_caller_identity()["Account"]
    lam = session.client("lambda")
    iam = session.client("iam")
    sch = session.client("scheduler")

    if args.destroy:
        for call, kwargs in (
            (sch.delete_schedule, {"Name": SCHEDULE_NAME}),
            (lam.delete_function, {"FunctionName": FUNCTION_NAME}),
        ):
            try:
                call(**kwargs)
                print(f"deleted {kwargs}")
            except ClientError as exc:
                print(f"skip {kwargs}: {exc.response['Error']['Code']}")
        return 0

    role_arn = ensure_role(iam, ROLE_NAME, TRUST_POLICY, args.region, account)
    sched_role_arn = ensure_role(
        iam, "builtwatch-scheduler-role", SCHEDULER_TRUST, args.region, account
    )

    package = build_zip()
    env = {
        "Variables": {
            "BW_REGISTRY": "sources/registry.yaml",
            "BW_REPLAY": "replay",
            "BW_SCREEN_MODEL": "us.amazon.nova-lite-v1:0",
            "BW_ASSESS_MODEL": "us.amazon.nova-pro-v1:0",
            "BW_MAX_RUN_USD": "0.50",
            "BW_MAX_DAY_USD": "0.50",
            "BW_MAX_MONTH_USD": "2.00",
        }
    }
    try:
        lam.create_function(
            FunctionName=FUNCTION_NAME,
            Runtime=RUNTIME,
            Role=role_arn,
            Handler="runner.lambda_handler",
            Code={"ZipFile": package},
            Timeout=600,
            MemorySize=1024,
            Architectures=["arm64"],
            Environment=env,
        )
        print(f"created function {FUNCTION_NAME}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceConflictException":
            raise
        lam.update_function_code(FunctionName=FUNCTION_NAME, ZipFile=package)
        lam.get_waiter("function_updated").wait(FunctionName=FUNCTION_NAME)
        lam.update_function_configuration(FunctionName=FUNCTION_NAME, Environment=env)
        print(f"updated function {FUNCTION_NAME}")

    fn_arn = lam.get_function(FunctionName=FUNCTION_NAME)["Configuration"]["FunctionArn"]
    schedule_args = {
        "Name": SCHEDULE_NAME,
        "ScheduleExpression": args.schedule,
        "FlexibleTimeWindow": {"Mode": "FLEXIBLE", "MaximumWindowInMinutes": 30},
        "Target": {
            "Arn": fn_arn,
            "RoleArn": sched_role_arn,
            "Input": json.dumps({"mode": args.mode}),
        },
        "Description": "BuiltWatch nightly watch pass",
    }
    try:
        sch.create_schedule(**schedule_args)
        print(f"created schedule {SCHEDULE_NAME}: {args.schedule}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ConflictException":
            raise
        sch.update_schedule(**schedule_args)
        print(f"updated schedule {SCHEDULE_NAME}: {args.schedule}")

    iam.put_role_policy(
        RoleName="builtwatch-scheduler-role",
        PolicyName="invoke-builtwatch",
        PolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {"Effect": "Allow", "Action": "lambda:InvokeFunction", "Resource": fn_arn}
                ],
            }
        ),
    )
    print("\ndone. invoke manually with:")
    print(f"  aws lambda invoke --function-name {FUNCTION_NAME} "
          f"--payload '{{\"mode\":\"replay\"}}' --cli-binary-format raw-in-base64-out /dev/stdout")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
