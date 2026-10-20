"""Update existing BuiltWatch functions without recreating infrastructure or secrets.

Backups contain private configuration and stay under ignored data/. A matching expected
account is mandatory. --prepare-only creates validated archives without cloud writes.
"""

from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path

import boto3
import httpx

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = ("builtwatch-accounts-worker", "builtwatch-accounts-api")
POLICY_NAME = "builtwatch-no-paid-inference"
DENY = {
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "NoPaidInference", "Effect": "Deny", "Action": ["bedrock:*"], "Resource": "*"},
    ],
}
BRIEF_WORKER = "builtwatch-accounts-worker"
BRIEF_MODEL = "amazon.nova-lite-v1:0"


def brief_policy(account: str) -> dict:
    """Bedrock stays denied except one cheap model, invoked by the scan worker only."""
    allowed = [
        f"arn:aws:bedrock:*:{account}:inference-profile/us.{BRIEF_MODEL}",
        f"arn:aws:bedrock:*::foundation-model/{BRIEF_MODEL}",
    ]
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "OnlyBriefModel",
                "Effect": "Deny",
                "Action": ["bedrock:*"],
                "NotResource": allowed,
            },
            {
                "Sid": "BriefModelInvoke",
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel"],
                "Resource": allowed,
            },
        ],
    }


# AI impact briefs: a hard monthly allowance shared by every workspace.
BRIEF_ENV = {
    "BW_AI_BRIEFS": "on",
    "BW_AI_BRIEF_MODEL": f"us.{BRIEF_MODEL}",
    "BW_AI_BRIEF_MONTH_COUNT": "300",
    "BW_AI_BRIEF_MONTH_USD": "0.50",
}
FREE_ENV = {
    "BW_INFERENCE_MODE": "rules",
    "BW_MAX_RUN_USD": "0",
    "BW_MAX_DAY_USD": "0",
    "BW_MAX_MONTH_USD": "0",
}


def package(previous: bytes) -> bytes:
    replacements = {
        str(path.relative_to(ROOT / "src")): path.read_bytes()
        for path in (ROOT / "src/builtwatch").rglob("*.py")
    }
    replacements["accounts_runner.py"] = (ROOT / "infra/accounts_runner.py").read_bytes()
    for directory in ("sources", "replay"):
        replacements.update(
            {str(p.relative_to(ROOT)): p.read_bytes() for p in (ROOT / directory).rglob("*.yaml")}
        )
    data = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(previous)) as old,
        zipfile.ZipFile(
            data,
            "w",
            zipfile.ZIP_DEFLATED,
        ) as new,
    ):
        for item in old.infolist():
            if item.filename not in replacements and "__pycache__" not in item.filename:
                new.writestr(item, old.read(item.filename))
        for name, content in replacements.items():
            new.writestr(name, content)
    with zipfile.ZipFile(data) as archive:
        if archive.testzip():
            raise RuntimeError("Deployment package failed CRC validation")
    return data.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--backup-directory", default="free-rollout")
    briefs = parser.add_mutually_exclusive_group()
    briefs.add_argument(
        "--ai-briefs",
        dest="ai_briefs",
        action="store_const",
        const=True,
        help="Allow the scan worker to call Nova Lite for capped AI impact briefs.",
    )
    briefs.add_argument(
        "--no-ai-briefs",
        dest="ai_briefs",
        action="store_const",
        const=False,
        help="Turn AI impact briefs off and deny all Bedrock again.",
    )
    args = parser.parse_args()
    if Path(args.backup_directory).name != args.backup_directory or args.backup_directory in {
        ".", "..",
    }:
        parser.error("--backup-directory must be a folder name inside ignored data/")
    session = boto3.Session(region_name="us-east-1")
    if session.client("sts").get_caller_identity()["Account"] != args.account:
        raise RuntimeError("AWS account does not match --account")
    lam, iam = session.client("lambda"), session.client("iam")
    directory = ROOT / "data" / args.backup_directory
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    configs, archives = {}, {}
    for name in FUNCTIONS:
        old_zip, old_config = directory / (name + ".zip"), directory / (name + ".json")
        # Never replace the pre-rollout backup during a retry.
        if not old_zip.exists() or not old_config.exists():
            current = lam.get_function(FunctionName=name)
            content = httpx.get(current["Code"]["Location"], timeout=60).raise_for_status().content
            old_zip.write_bytes(content)
            old_config.write_text(json.dumps(current["Configuration"], default=str))
            old_zip.chmod(0o600)
            old_config.chmod(0o600)
        configs[name] = json.loads(old_config.read_text())
        archives[name] = package(old_zip.read_bytes())
        path = directory / (name + "-free.zip")
        path.write_bytes(archives[name])
        path.chmod(0o600)
        print(f"Prepared {name}: {len(archives[name])} bytes", flush=True)
    if args.prepare_only:
        return
    # Deny inference before code/config changes, including retired BuiltWatch functions.
    roles = set()
    for page in lam.get_paginator("list_functions").paginate():
        for function in page["Functions"]:
            if function["FunctionName"].startswith("builtwatch-"):
                roles.add(function["Role"].rsplit("/", 1)[-1])
    if args.ai_briefs is None:
        # Neither flag: keep whatever the live worker has, so a routine code deploy never
        # silently switches briefs on or off.
        live = lam.get_function_configuration(FunctionName=BRIEF_WORKER)
        live_env = live.get("Environment", {}).get("Variables", {})
        args.ai_briefs = live_env.get("BW_AI_BRIEFS") == "on"
    print(f"AI impact briefs: {'on (Nova Lite, capped)' if args.ai_briefs else 'off'}", flush=True)
    worker_role = configs[BRIEF_WORKER]["Role"].rsplit("/", 1)[-1]
    for role in sorted(roles):
        if args.ai_briefs and role == worker_role:
            policy = brief_policy(args.account)
            iam.put_role_policy(
                RoleName=role, PolicyName=POLICY_NAME, PolicyDocument=json.dumps(policy)
            )
            print(f"Denied Bedrock on {role} except {BRIEF_MODEL} for AI briefs", flush=True)
            continue
        iam.put_role_policy(RoleName=role, PolicyName=POLICY_NAME, PolicyDocument=json.dumps(DENY))
        print(f"Denied Bedrock on {role}", flush=True)
    for name in FUNCTIONS:
        current = lam.get_function_configuration(FunctionName=name)
        lam.update_function_configuration(
            FunctionName=name,
            RevisionId=current["RevisionId"],
            Environment={
                "Variables": {
                    **{
                        k: v
                        for k, v in current.get("Environment", {}).get("Variables", {}).items()
                        if not k.startswith("BW_AI_BRIEF")
                    },
                    **FREE_ENV,
                    **(BRIEF_ENV if args.ai_briefs else {}),
                }
            },
        )
        lam.get_waiter("function_updated_v2").wait(FunctionName=name)
        current = lam.get_function_configuration(FunctionName=name)
        result = lam.update_function_code(
            FunctionName=name,
            RevisionId=current["RevisionId"],
            ZipFile=archives[name],
        )
        lam.get_waiter("function_updated_v2").wait(FunctionName=name)
        check = lam.get_function_configuration(FunctionName=name)
        if check["CodeSha256"] != result["CodeSha256"]:
            raise RuntimeError("Deployed code digest differs")
        if any(check["Environment"]["Variables"].get(k) != v for k, v in FREE_ENV.items()):
            raise RuntimeError("Zero-inference configuration was not preserved")
        print(f"Verified {name}: rules mode, zero model ceilings, code digest matches", flush=True)


if __name__ == "__main__":
    main()
