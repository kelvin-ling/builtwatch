# BuiltWatch after the competition

The owner ended the competition freeze and authorized changes and deployment on
14 October 2026. The submission documents are historical; they do not constrain new
product changes. Concurrency locks still protect simultaneous writes to private data.

## Default mechanism

`BW_INFERENCE_MODE=rules` performs no inference calls. It fetches the existing curated
registry, compares successful snapshots, and matches added material passages against
explicitly recorded service or technology names. The first observation establishes a
baseline. Matches carry exact passages, exact app facts and an explicit request for
review. They do not assert impact, legal applicability or adoption status.

Baseline observations, unchanged pages, navigation-only changes and unverified quotations
cannot create new rule candidates. Repeat observations are cached and deduplicated.
Source failures remain visible. Pure deletions, implicit dependencies, synonyms outside
the routing dictionary and general regulatory applicability may be missed. A quiet run
is not a safety or compliance determination. Existing AI findings remain historical
records; new runs and findings identify the rules method.

For deeper review, use the existing copy/export or scoped project-agent connection.
The agent's own subscription or usage terms apply; BuiltWatch does not invoke or pay
that agent. Text intake now makes a basic literal draft for human review. Importing a
structured profile prepared by the project agent remains the highest-fidelity route.
Summary updates preserve existing structured facts; use the editor or JSON import to
change or remove dependencies, actions and operating conditions.

## Why this approach

This removes recurring inference charges without adding a service account, paid plan,
always-on model server or another processor for private profiles. AWS accounts and
stored data stay in place. The tradeoff is narrower automated interpretation.

Alternatives checked on 14 October 2026:

- [Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/platform/pricing/)
  includes 10,000 neurons/day; paid usage and some models require a paid plan. It is an
  optional future semantic layer with a hard application quota, not an unlimited free
  replacement. The current Sites service exposes no AI binding or Cloudflare account key.
- [Gemini API](https://ai.google.dev/gemini-api/docs/pricing) offers model-specific free
  quotas; its free tier uses content for product improvement. Sending private workspace
  profiles there would change their handling.
- [Groq](https://console.groq.com/docs/rate-limits) offers a rate-limited free plan and
  requires an account/key. Do not silently fall back to a paid plan when throttled.
- Local open models avoid token charges but require persistent compute; a new hosted
  instance would add idle cost and operations to this small pilot.

## Cost controls and deployment

The account API and worker are configured with `BW_INFERENCE_MODE=rules` and zero
per-run/day/month model ceilings. BuiltWatch Lambda execution roles deny `bedrock:*`;
a future provider change must deliberately update policy as well as configuration.
Legacy model implementations are retained for historical tests and portability. They
are unreachable by default and the paid model factory rejects the rules mode.

Request, registration, draft, profile-count and manual-check cooldown limits remain.
The daily billing monitor and alerts remain; an old paid allowance does not block
zero-inference matching. AWS Lambda, DynamoDB, Cognito, domain registration, logging,
network and Sites hosting can still incur costs. There is no hard total invoice cap.
No new paid subscription or compute instance is provisioned by this change.

Use `infra/deploy_free.py --account <expected-account>` for this rollout. It backs up
each deployed package and configuration under ignored `data/`, patches application
files while retaining installed Linux dependencies, updates only existing functions,
and preserves secrets, URLs, identity, data, schedules and concurrency. Existing
BuiltWatch execution roles receive the inference deny. Backups are local operator
material and must never be committed.

## Status observed before this release

The site was public at https://builtwatch.org, Sites version 92. Two populated
workspaces held seven apps. Last completed checks were 8–10 October; subsequent checks
had paused at the paid allowances. The 14 October cached whole-account billing snapshot
reported USD 36.17 before credits/refunds. A single fresh service-grouped Cost Explorer
query showed a USD 32 Amazon Registrar charge. Billing reports can differ as data
settles; this is not a BuiltWatch-only cost or final invoice. The fresh query itself may
incur the standard USD 0.01 API charge.

The public Impact API was returning HTTP 500: Sites prohibits its default cache lookup.
The optional cache now fails safely. A fresh dependency installation also exposed the
removed selectolax Modest parser; retrieval uses the supported Lexbor parser instead.

## Verified production release — 14 October 2026

Sites version 93 deployed successfully (15 October 02:04 UTC) from source
`d488c31225fe59acb28fff187aea204637402211`; https://builtwatch.org remains public.
The public Impact endpoint returned HTTP 200, anonymous workspace access returned 401,
and the updated frontend was verified over HTTPS. Both account Lambdas are active in
rules mode with zero model ceilings. IAM simulation returned `explicitDeny` for both
Bedrock invoke actions on both active roles, without invoking a model.

The scheduled entrypoint was exercised once. Both populated workspaces completed checks
across all 21 sources, with no failed fetches, no model, and USD 0 inference usage:
21 app/source comparisons produced three candidates for the one-app workspace; 126
comparisons produced eight candidates for the six-app workspace. These are possible
matches for review, not verified impacts. Existing profiles and historical records remain.

Validation: 157 Python tests, 49 Node/runtime tests, Ruff, JavaScript syntax, production
build, deployment-package CRC and deployed-code digests passed. Backups of code and
configuration remain under ignored private `site-source/data/`. No new paid provider,
subscription or compute instance was created. A signed-in browser visual review was not
performed; authentication and gateway boundaries were tested through the runtime suite.
