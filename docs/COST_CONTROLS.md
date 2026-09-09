# BuiltWatch cost controls

The owner targets **CAD 25 per month**. This is a conservative operating target, not a
provider-enforced invoice cap. Billing is delayed and infrastructure, taxes, exchange
rates, other projects and hosting charges can fall outside model estimates.

| Control | Production setting |
|---|---:|
| Shared monthly model reservations, all workspaces | USD 5 |
| Per-workspace model thresholds | USD 2/month, 0.50/day, 0.25/check |
| Intake threshold | USD 0.02/draft, five drafts/day/account |
| Global reported AWS cost pause | USD 10/month |
| AWS Budget notification backstop | USD 12/month |
| Admission | 25 workspaces, ten apps each |
| Registration | 100 lifetime attempts |
| Gateway requests | 180/minute, 10,000/day; 300/day/account |
| Authentication | 200/day global; 20/hour/IP; 10/hour/email |
| Verification/recovery requests | 20/day global |
| Lambda concurrency | Four API, two workers, one cost monitor |
| Owner dashboard requests | 100/day, separate from normal traffic |

The daily cost monitor reads whole-account unblended cost before credits/refunds, including
other projects. It caches a daily breakdown, Cognito's estimated registration count,
admitted workspaces, app counts and job status totals. Dashboard visits use this cache;
they do not query Cost Explorer. CAD is displayed using a 1.5 planning multiplier, not a
live exchange rate. The monitor runs at 6 a.m. Toronto; daily app checks run at 7 a.m.

Paid checks pause if reported cost reaches USD 10, billing retrieval fails, the cached
status is missing or older than 48 hours, the owner pauses them, or the shared model
reserve cannot accept another USD 1 reservation. Actual estimated model use is settled
after the task; a timed-out task keeps its full reservation. Already-running calls can
finish and can overshoot a per-call threshold. An owner resume does not override the
automatic cost guard. The budget alert alone does not stop AWS services.

Warnings start at USD 7 account cost or USD 4 model reservations. A completed day with
at least USD 1 and more than three times its recent baseline triggers an unusual-spend
warning. SNS sends at most one warning per day after the recipient confirms the AWS
subscription email. Confirmation status appears in the owner dashboard. Billing and
email delivery can be delayed; there is no instant fraud-detection guarantee.

When paid checks pause, stored workspaces and ordinary imports/exports remain usable
within request limits. Anonymous demo interactions and bulk demo imports run locally
without models. The downloadable offline demo also works without the hosted service.
Hosted availability remains subject to provider quotas/outages; unrestricted free cloud
traffic is not guaranteed. Sites hosting is outside the AWS usage meter.

The account gateway is IAM- and HMAC-protected; unsigned callers cannot invoke its AWS
Function URL. Profile data stays in tenant partitions. Source retrieval uses a curated
registry; user-provided URLs cannot trigger arbitrary fetching. Bulk imports validate
all profiles before saving, use stable IDs for safe retries, and make no model calls.
