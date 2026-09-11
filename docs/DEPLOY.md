# Deploy and re-scan runbook

Every command here was executed or dry-run on 10 September 2026 against account
`[aws-account-redacted]`. Follow it top to bottom; it is safe to hand to another agent.

**Read [ISSUES.md](ISSUES.md) first.** Deploying is what makes the BW-1/BW-2 fixes take
effect, and it has a visible consequence described in step 4.

---

## 0. Credentials

```bash
cd <local-user>/Downloads/Agents-for-Humans/builtwatch
export AWS_PROFILE=[aws-profile-redacted] AWS_REGION=us-east-1
eval "$(aws configure export-credentials --format env)"
aws sts get-caller-identity --query Account --output text     # must print [aws-account-redacted]
```

**Two SSO token caches exist** and `boto3` picks the expired one while the AWS CLI picks
the valid one. The `eval` line above is not optional — without it Python fails with
`TokenRetrievalError: Token has expired and refresh failed`.

If the CLI itself fails, the session has expired and **a human must run**:

```bash
aws sso login --profile [aws-profile-redacted]
```

No agent can complete that; it needs a browser approval. Stop and ask.

`deploy_accounts.py` asserts the account id and refuses to run anywhere else.

---

## 1. Pre-flight

```bash
.venv/bin/python -m pytest tests/ -q          # expect 120 passed
.venv/bin/python -m ruff check src tests infra # expect All checks passed!
```

Do not deploy on a red suite.

---

## 2. Build the package

```bash
.venv/bin/python infra/deploy_accounts.py --build-only
```

Writes `data/accounts.zip` (~31 MB, linux/arm64 dependencies, gitignored). Makes **no AWS
calls**. Confirm the build actually carries the fix you intend to ship:

```bash
.venv/bin/python -c "
import zipfile; s=zipfile.ZipFile('data/accounts.zip').read('builtwatch/quality.py').decode()
print([l for l in s.splitlines() if l.startswith('QUALITY_VERSION')])
print('affected_product_undeclared:', 'affected_product_undeclared' in s)"
```

Expect `['QUALITY_VERSION = 4']` and `True`.

---

## 3. Deploy

```bash
.venv/bin/python infra/deploy_accounts.py
```

Idempotent — creates on first run, updates thereafter. Updates
`builtwatch-accounts-api` and `builtwatch-accounts-worker`, reasserts reserved concurrency
(4 / 2), IAM roles, the DynamoDB table and the daily schedule. Prints
`Account backend and daily schedule ready.`

Confirm both functions actually took the new code:

```bash
.venv/bin/python -c "
import boto3
l=boto3.client('lambda',region_name='us-east-1')
for f in ['builtwatch-accounts-api','builtwatch-accounts-worker']:
    c=l.get_function_configuration(FunctionName=f)
    print(f, c['LastModified'], c['State'], c.get('LastUpdateStatus'))"
```

---

## 4. Re-scan — required, not optional

**QUALITY_VERSION withholds every finding from a superseded generation.** All 43 stored
findings across the two live tenants are generation 0. The moment step 3 lands, the
workspace shows **zero findings** until a scan regenerates them.

So do not stop after step 3. Trigger a full pass immediately:

```bash
.venv/bin/python -c "
import boto3, json
r=boto3.client('lambda',region_name='us-east-1').invoke(
    FunctionName='builtwatch-accounts-api',
    InvocationType='RequestResponse',
    Payload=json.dumps({'task':'daily'}).encode())
print(r['StatusCode'], r['Payload'].read().decode()[:300])"
```

`{"task":"daily"}` fans out one `{"task":"scan","tenant":...}` per admitted tenant to the
worker, which is where the assessment actually runs.

**Cost:** roughly $0.25 per tenant, so ~$0.50 total, drawn from the $5 monthly shared
reserve (`GLOBAL_MONTH_LIMIT`). Each scan reserves $1.00 up front and settles the real
figure afterwards, so two concurrent tenants fit inside the reserve but a third would be
refused until one settles. That is intended behaviour, not a failure.

Scans are asynchronous. Watch progress:

```bash
aws logs tail /aws/lambda/builtwatch-accounts-worker --since 10m --follow
```

---

## 5. Verify

```bash
.venv/bin/python -c "
import boto3, json, collections
from boto3.dynamodb.conditions import Key
import sys; sys.path.insert(0,'src')
from builtwatch.quality import QUALITY_VERSION
t=boto3.resource('dynamodb',region_name='us-east-1').Table('builtwatch-accounts')
for seat in t.query(KeyConditionExpression=Key('pk').eq('SEATS'))['Items']:
    pk='USER#'+seat['sk']
    items=[json.loads(i['payload']) for i in
           t.query(KeyConditionExpression=Key('pk').eq(pk)&Key('sk').begins_with('finding#'))['Items']]
    cur=[f for f in items if f.get('quality_version',0)>=QUALITY_VERSION]
    rel=collections.Counter(f['relevance'] for f in cur)
    job=t.get_item(Key={'pk':pk,'sk':'job'}).get('Item',{})
    print(seat['sk'][:12], 'job=', json.loads(job.get('payload','{}')).get('status'),
          '| current-generation findings:', len(cur), dict(rel))"
```

Success looks like: `job= complete`, a non-zero count of current-generation findings, and
**no finding whose inference names a product absent from its passport**. Specifically, the
`CVE-2026-85880` Windows finding must not reappear as `relevant` — that is the BW-1
regression, and its absence is the whole point of the deploy.

Then load the site and confirm findings render:
`https://builtwatch.org/`

---

## Admin dashboard

`https://builtwatch.org/#admin`

Server-gated on `session.is_admin`, which is true only for the tenant whose id matches the
`BW_OWNER_ACCOUNT` environment variable on `builtwatch-accounts-api` (currently
`e4e140e3b676…`, derived from the owner's verified Cognito subject). Signing in as any
other account will not reveal it, and the nav entry stays hidden. There is also an
**Owner dashboard** button once signed in as the owner.

It shows reported account spend, the shared reserve, active workspaces, per-tenant job
status, monitor warnings, and the manual pause control.

---

## Rolling back

There is no automated rollback. To revert code, check out the previous commit, rebuild
(step 2) and redeploy (step 3).

To stop all paid activity immediately without deploying anything, set the manual pause
flag — `reserve_budget()` refuses every scan while it is set:

```bash
.venv/bin/python -c "
import boto3
boto3.resource('dynamodb',region_name='us-east-1').Table('builtwatch-accounts').put_item(
    Item={'pk':'ADMIN','sk':'control','paused':True})
print('paid checks paused')"
```

Remove the item (or set `paused` false) to resume.
