"""Give the edge proxy only URL-invoke permission; close direct anonymous invocation.

Run once without flags to provision credentials. Configure them as Sites secrets and
verify the signed Worker before running --enable. Never grants model or database access.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path

import boto3

NAME = "builtwatch-sites-proxy"
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable", action="store_true")
    args = parser.parse_args()
    s = boto3.Session(region_name="us-east-1")
    account = s.client("sts").get_caller_identity()["Account"]
    assert account == "[aws-account-redacted]"
    lam = s.client("lambda")
    if args.enable:
        lam.update_function_url_config(FunctionName="builtwatch-accounts-api", AuthType="AWS_IAM")
        for sid in ["signed-proxy-url", "signed-proxy-invoke"]:
            with contextlib.suppress(lam.exceptions.ResourceNotFoundException):
                lam.remove_permission(FunctionName="builtwatch-accounts-api", StatementId=sid)
        # The retired shared-key endpoint must not remain an anonymous billing surface.
        lam.update_function_url_config(FunctionName="builtwatch-workspace", AuthType="AWS_IAM")
        for sid in ["web-url", "web-url-invoke"]:
            with contextlib.suppress(lam.exceptions.ResourceNotFoundException):
                lam.remove_permission(FunctionName="builtwatch-workspace", StatementId=sid)
        print("Current and retired API URLs now require AWS IAM authorization.")
        return
    iam = s.client("iam")
    with contextlib.suppress(iam.exceptions.EntityAlreadyExistsException):
        iam.create_user(UserName=NAME, Tags=[{"Key": "Project", "Value": "BuiltWatch"}])
    arn = f"arn:aws:lambda:us-east-1:{account}:function:builtwatch-accounts-api"
    iam.put_user_policy(
        UserName=NAME,
        PolicyName="InvokeOnlyBuiltWatchURL",
        PolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {"Effect": "Allow", "Action": "lambda:InvokeFunctionUrl", "Resource": arn},
                    {
                        "Effect": "Allow",
                        "Action": "lambda:InvokeFunction",
                        "Resource": arn,
                        "Condition": {"Bool": {"lambda:InvokedViaFunctionUrl": "true"}},
                    },
                ],
            }
        ),
    )
    path = ROOT / "data/accounts-access.json"
    cfg = json.loads(path.read_text())
    if not cfg.get("aws_access_key_id"):
        key = iam.create_access_key(UserName=NAME)["AccessKey"]
        cfg.update(
            aws_access_key_id=key["AccessKeyId"], aws_secret_access_key=key["SecretAccessKey"]
        )
        path.write_text(json.dumps(cfg))
        os.chmod(path, 0o600)
    print("Scoped proxy credentials ready in private deployment settings.")


if __name__ == "__main__":
    main()
