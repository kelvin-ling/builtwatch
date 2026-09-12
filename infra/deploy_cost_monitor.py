"""Provision the owner-approved daily cost guard and email channel."""

import contextlib
import io
import json
import zipfile
from pathlib import Path

import boto3
from deploy_web import role

s = boto3.Session(region_name="us-east-1")
account = s.client("sts").get_caller_identity()["Account"]
assert account == "[aws-account-redacted]"
name = "builtwatch-cost-monitor"
topic = s.client("sns").create_topic(Name="builtwatch-owner-cost-alerts")["TopicArn"]
subs = s.client("sns").list_subscriptions_by_topic(TopicArn=topic)["Subscriptions"]
if not any(x.get("Endpoint") == "[owner-email-redacted]" for x in subs):
    s.client("sns").subscribe(TopicArn=topic, Protocol="email", Endpoint="[owner-email-redacted]")
cfg = json.loads(Path("data/cognito-access.json").read_text())
policy = {
    "Version": "2012-10-17",
    "Statement": [
        {"Effect": "Allow", "Action": ["ce:GetCostAndUsage"], "Resource": "*"},
        {
            "Effect": "Allow",
            "Action": ["cognito-idp:DescribeUserPool"],
            "Resource": f"arn:aws:cognito-idp:us-east-1:{account}:userpool/{cfg['pool_id']}",
        },
        {
            "Effect": "Allow",
            "Action": ["sns:Publish", "sns:ListSubscriptionsByTopic"],
            "Resource": topic,
        },
        {
            "Effect": "Allow",
            "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query"],
            "Resource": f"arn:aws:dynamodb:us-east-1:{account}:table/builtwatch-accounts",
        },
        {
            "Effect": "Allow",
            "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
            "Resource": f"arn:aws:logs:us-east-1:{account}:log-group:/aws/lambda/{name}:*",
        },
    ],
}
arn = role(s.client("iam"), name + "-role", "lambda.amazonaws.com", policy)
logs = s.client("logs")
with contextlib.suppress(logs.exceptions.ResourceAlreadyExistsException):
    logs.create_log_group(logGroupName="/aws/lambda/" + name)
logs.put_retention_policy(logGroupName="/aws/lambda/" + name, retentionInDays=7)
b = io.BytesIO()
with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
    z.write("infra/cost_monitor.py", "cost_monitor.py")
lam = s.client("lambda")
params = dict(
    FunctionName=name,
    Handler="cost_monitor.lambda_handler",
    Timeout=60,
    MemorySize=128,
    Environment={
        "Variables": {
            "BW_TABLE": "builtwatch-accounts",
            "BW_USER_POOL": cfg["pool_id"],
            "BW_ALERT_TOPIC": topic,
        }
    },
)
try:
    lam.create_function(**params, Runtime="python3.12", Role=arn, Code={"ZipFile": b.getvalue()})
except lam.exceptions.ResourceConflictException:
    lam.update_function_code(FunctionName=name, ZipFile=b.getvalue())
    lam.get_waiter("function_updated_v2").wait(FunctionName=name)
    lam.update_function_configuration(**params)
lam.get_waiter("function_active_v2").wait(FunctionName=name)
lam.put_function_concurrency(FunctionName=name, ReservedConcurrentExecutions=1)
scheduler = s.client("scheduler")
schedule_role = role(
    s.client("iam"),
    name + "-scheduler",
    "scheduler.amazonaws.com",
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "lambda:InvokeFunction",
                "Resource": f"arn:aws:lambda:us-east-1:{account}:function:{name}",
            }
        ],
    },
)
params = {
    "Name": name + "-daily",
    "ScheduleExpression": "cron(0 6 * * ? *)",
    "ScheduleExpressionTimezone": "America/Toronto",
    "State": "ENABLED",
    "FlexibleTimeWindow": {"Mode": "OFF"},
    "Target": {
        "Arn": f"arn:aws:lambda:us-east-1:{account}:function:{name}",
        "RoleArn": schedule_role,
        "Input": "{}",
        "RetryPolicy": {"MaximumRetryAttempts": 0, "MaximumEventAgeInSeconds": 900},
    },
}
try:
    scheduler.create_schedule(**params)
except scheduler.exceptions.ConflictException:
    scheduler.update_schedule(**params)
bud = s.client("budgets")
old = bud.describe_budget(AccountId=account, BudgetName="builtwatch-monthly-20usd")["Budget"]
allowed = [
    "BudgetName",
    "BudgetLimit",
    "CostFilters",
    "CostTypes",
    "TimeUnit",
    "TimePeriod",
    "BudgetType",
    "PlannedBudgetLimits",
    "AutoAdjustData",
    "FilterExpression",
    "Metrics",
]
new = {k: v for k, v in old.items() if k in allowed}
new["BudgetLimit"] = {"Amount": "5", "Unit": "USD"}
bud.update_budget(AccountId=account, NewBudget=new)
print(
    "Daily monitor configured; BuiltWatch budget lowered to USD 5. "
    "Email confirmation may be required."
)
r = lam.invoke(FunctionName=name, Payload=b"{}")
print("Initial monitor result:", r["Payload"].read().decode())
