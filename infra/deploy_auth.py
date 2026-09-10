"""Provision the email-only Cognito Lite client; no SMS, paid email or hosted domain."""

import json
import os
from pathlib import Path

import boto3

PASSWORD_POLICY = {
    "MinimumLength": 12,
    "RequireUppercase": True,
    "RequireLowercase": True,
    "RequireNumbers": True,
    "RequireSymbols": False,
}
TOKEN_VALIDITY_UNITS = {
    "AccessToken": "minutes",
    "IdToken": "minutes",
    "RefreshToken": "days",
}

session = boto3.Session(region_name="us-east-1")
assert session.client("sts").get_caller_identity()["Account"] == "[aws-account-redacted]"

cognito = session.client("cognito-idp")
access_path = Path("data/cognito-access.json")
if access_path.exists():
    print("Existing Cognito settings retained.")
    raise SystemExit

pools = cognito.list_user_pools(MaxResults=60)["UserPools"]
pool = next((x["Id"] for x in pools if x["Name"] == "builtwatch-public"), None)
if not pool:
    pool = cognito.create_user_pool(
        PoolName="builtwatch-public",
        UserPoolTier="LITE",
        UsernameAttributes=["email"],
        AutoVerifiedAttributes=["email"],
        UsernameConfiguration={"CaseSensitive": False},
        Schema=[
            {
                "Name": "email",
                "AttributeDataType": "String",
                "Required": True,
                "Mutable": True,
            }
        ],
        Policies={"PasswordPolicy": PASSWORD_POLICY},
        MfaConfiguration="OFF",
        EmailConfiguration={"EmailSendingAccount": "COGNITO_DEFAULT"},
        AccountRecoverySetting={
            "RecoveryMechanisms": [{"Priority": 1, "Name": "verified_email"}]
        },
        UserPoolTags={"Project": "BuiltWatch"},
    )["UserPool"]["Id"]

clients = cognito.list_user_pool_clients(UserPoolId=pool, MaxResults=60)["UserPoolClients"]
existing = next((x for x in clients if x["ClientName"] == "builtwatch-server"), None)
if existing:
    client = cognito.describe_user_pool_client(
        UserPoolId=pool, ClientId=existing["ClientId"]
    )["UserPoolClient"]
else:
    client = cognito.create_user_pool_client(
        UserPoolId=pool,
        ClientName="builtwatch-server",
        GenerateSecret=True,
        ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
        PreventUserExistenceErrors="ENABLED",
        EnableTokenRevocation=True,
        AccessTokenValidity=5,
        IdTokenValidity=5,
        RefreshTokenValidity=1,
        TokenValidityUnits=TOKEN_VALIDITY_UNITS,
        ReadAttributes=["email", "email_verified", "sub"],
        WriteAttributes=["email"],
    )["UserPoolClient"]

access_path.write_text(
    json.dumps(
        {
            "pool_id": pool,
            "client_id": client["ClientId"],
            "client_secret": client["ClientSecret"],
        }
    )
)
os.chmod(access_path, 0o600)
print("Cognito Lite email registration configured. Server-only client secret saved privately.")
