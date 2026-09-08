# BuiltWatch cost controls

The deployment minimizes idle compute; it does not guarantee a zero bill or a hard
account-wide spending cap. The owner-approved budget recorded in the earlier handoff is
$20/month. The web deployment uses lower model thresholds:

| Control | Deployed value |
|---|---:|
| Estimated model threshold per scan | $0.25 |
| Estimated model threshold per UTC day | $0.50 |
| Estimated model threshold per UTC month | $10.00 |
| Manual scan cooldown | 30 minutes |
| Concurrent Lambda invocations | 1 (required for storage correctness) |
| Profiles | 10 |
| Source registry | 11 curated sources |
| Agent iterations per assessment | 8 |
| Scheduled scan | Daily, 7 a.m. Toronto |
| Log retention | 7 days |
| Old S3 checkpoint versions | 7 days |

The cost meter checks prior usage before each call. Usage/pricing are estimates and a
single in-flight model call can overshoot a threshold. Calls are also bounded by output
tokens and iteration counts. Scans stop before the function timeout when the deadline
hook is reached, then persist partial progress. Unexpected hard termination remains a
limitation: a checkpoint not yet uploaded can lose recent progress and metering.

Public sample browsing makes no model calls. API calls require an owner bearer key
before storage access or model work. Unauthorized requests can still incur small Lambda
request/compute charges. AWS Budgets notifications are alerts, not automatic hard stops.

Profiles saved through the web form do not invoke AI. Only changed/unassessed
(profile, source, mode) pairs invoke models. The shared cost ledger survives cold starts
in an encrypted S3 checkpoint. All invocations are serialized; keep concurrency at 1.

Storage, Lambda requests/duration, bandwidth, logs, and scheduling may incur charges
according to the AWS account's pricing and free-tier eligibility. There is no provisioned
concurrency or always-on VM. At this small scale these should be modest, but actual costs
must be monitored in AWS Billing. Sites hosting is outside the AWS usage meter.

Earlier CLI measurements reported approximately $0.25 for 3 systems x 11 replay sources;
those are historical measurements, not a promise for each new scan. Reading replay files
is offline; running the real model pipeline over them still costs money.
