# Canonical-host and crawler-policy release — 12 September 2026

Sites version 78 is live at `https://builtwatch.org/`. The generated
`builtwatch.kelvinlingac.chatgpt.site` hostname now returns a 301 to the custom domain,
preserving paths and query strings. The public HTML emits one canonical URL and
`/robots.txt` allows the public demo while excluding `/api/`. Worker and asset tests
cover the redirect and policy; 147 Python tests and 45 Node/runtime tests pass. No AWS
backend code or paid scan changed in this release.

# Verified categorized-sources and modal-layout release — 10 September 2026

Public Sites version 21 deployed successfully from
`0fce94466a0756fe7e5114933c263a79be5f4d01`. Watched sources are grouped by category,
with source counts and category-level fetch failures. Review-dialog actions now occupy a
separate footer, so expanded evidence scrolls without passing underneath the buttons.
The live HTML uses the `?v=20` asset key and the served application and stylesheet were
verified against the repository. The AWS backend and paid scans were not repeated.

# Verified actionable-only and automatic-check release — 9 September 2026

Public Sites version 14 deployed successfully at 00:07 UTC on 10 September.
Source: `dea4d7321825af6977d463d5523c8636a492f50e`.
Version: `appgprj_6a9fa33453988191895d1c0403f10071~appgver_8966b527bc80819188a1dc5b09ffc0b4`.
Deployment: `appgdep_6aa1f4be51b08191bc64151e13b5f565`.

Needs attention now contains only open findings that require user action: grounded relevant
items or a missing app fact the user can supply. Not-relevant results, acknowledged items,
and evidence-validation failures are excluded. Source outages and incomplete runs remain
visible in Watched sources and Check history because they affect confidence, but no longer
clutter the action list. The guide and result key describe only the two visible action types.

The live AWS schedule was read back as ENABLED at 7:00 a.m. America/Toronto, targeting the
account API with `{"task":"daily"}`. A controlled production event exposed unreliable
assessment tool use, so the final assessment now receives bounded exact source passages and
the trusted app fact index directly. It has no model-controlled tools; every cited passage
and app fact is still validated against storage before a relevant result can surface.

After deploying that change, the same production daily event completed for both active
workspaces. The saved results were `complete`: one reported zero new findings; the other
reported zero new findings and one item needing more information. This was a real live-source
and Bedrock run, not replay or demo data. The production worker package matched the validated
source. 102 Python and 21 Node/runtime tests passed; Python lint, JavaScript syntax, build and
archive validation passed. The public page and final JavaScript copy were verified over HTTP.
No browser visual QA was performed.

# Verified clear-action interface release — 9 September 2026

Public Sites version 11 deployed successfully at 19:46 UTC.
Source: `bdc438f3cc4e5927cbab7ce1235ac265df7eb99b`.
Version: `appgprj_6a9fa33453988191895d1c0403f10071~appgver_4e704206ae408191919f0b640a5553c4`.
Deployment: `appgdep_6aa1b78a4218819191a820c5c8f3fea9`.

Every finding now states what is wrong, who owns the next step and what to do. Evidence
validation failures are explicitly a BuiltWatch problem with no app change requested;
missing app facts direct the user to verify and update the profile. Internal grounding
jargon is removed from the historical demo and hidden from details. Findings include a
plain result key and direct status labels. The overview's three-stage purpose flow now has
a restrained sequential animation with a reduced-motion fallback.

101 Python and 20 Node/runtime tests passed. The public app and stylesheet were verified
after deployment. The source also improves the wording stored by future assessments. The
AWS backend was not redeployed for that storage-only copy change because SSO authorization
was not completed; the deployed UI already translates both legacy and new forms, so the
visible fix is complete and future old-form results remain clear.

# Verified automation-map release — 9 September 2026

Public Sites version 10 deployed successfully at 16:18 UTC.
Source: `a25b3316e79999bafc84a6f0d50d76ac74e397ec`.
Version: `appgprj_6a9fa33453988191895d1c0403f10071~appgver_8778c37bf5ac8191a79fc8af250922d2`.
Deployment: `appgdep_6aa186c32f7c8191b293560ef6f22032`.

Every app now has a responsive automation map showing its first recorded service or data
input, automated work, human or system checkpoint, and real-world condition. When an open
finding exists, the outside development is visibly linked to the exact recorded stage used
by the assessment, with a path to its evidence and review question. Missing profile facts
remain explicitly unrecorded rather than inferred. The app profile modal carries the same
map. No schema, evidence, scan scope, scheduling, permissions, cost controls or AWS runtime
changed. 101 Python and 19 Node/runtime tests passed; source and test lint passed. No paid
model call or browser visual QA was performed.

# Verified app-impact release — 9 September 2026

Public Sites version 9 deployed successfully at 14:30 UTC.
Source: `8f2f2b579f073eb2f6f3b803f9a36131bcef9be2`.
Version: `appgprj_6a9fa33453988191895d1c0403f10071~appgver_5e005d57542c8191a42f1919dc439c6b`.
Deployment: `appgdep_6aa16d8174ec8191ae0493be1f96d3f6`.

Findings now lead with the app, show a recorded fact -> development -> possible consequence
-> review question, and group by app. Changed profile references are flagged. Existing
findings use stored facts/reasoning without paid rewriting. New relevant model outputs
require AppImpact anchored to a cited app fact; invalid/missing explanations are withheld.
Stored legacy Finding objects remain compatible. Cost ceilings and cache policy unchanged.
101 Python and 17 Node/runtime tests passed. New website assets and offline demo were
verified over HTTP; anonymous workspace access remains denied. No browser visual QA or
new paid model assessment was performed.

Hosting remains AWS application services + Sites/Cloudflare frontend/gateway. Sites custom
domain listing was empty. The custom-domain capability is available, but no hostname was
provided or attached. See CUSTOM_DOMAIN.md for DNS/TLS checks, fresh sign-in and preserved
account data. Do not claim the frontend has moved to AWS or that a domain purchase alone
completes cutover.

# Verified business-view release — 9 September 2026

Public Sites version 8 deployed successfully at 13:16 UTC.
Source: `c0d376c8893de52221d8bda3d74fa9fc43166325`.
Version: `appgprj_6a9fa33453988191895d1c0403f10071~appgver_2375a419c1f88191b6d48658ad52beab`.
Deployment: `appgdep_6aa15c41f2a0819182fcb5509bdfa1da`.

Business (default), Operations and Technical are presentation views, not access roles.
Account preferences persist in the tenant and merge without changing daily monitoring.
Business context uses existing actions/assumptions/constraints/regions; no new mandatory
profile fields. Intake and screening now include these conditions. FTC business-news
summaries are the twelfth fixed source, within the existing twelve-source ceiling.
A real safe fetch succeeded; a dated public replay is committed. No linked-article crawl.
The existing historical demo remains historical and does not pretend to assess new news.
All monthly cost guards remain unchanged. Switching views uses no model calls.

99 Python and 15 Node/runtime tests pass. Live verification confirmed the Business
default, saved Operations preference, unchanged paused-monitoring setting, rejection of
an admin view value, owner isolation and twelve-source registry. Temporary test data was
removed. Browser visual QA and a new paid model assessment were not performed.

# Verified release — 9 September 2026

Sites version 7 is public and succeeded at 2026-09-09 12:44 UTC.
Source: `7453039094dc6f5036fe5a7d18d70474af4deb72`.
Saved version: `appgprj_6a9fa33453988191895d1c0403f10071~appgver_1231b6d6762c81918cbea9fde53abf95`.
Deployment: `appgdep_6aa154a4cd188191b8f435bc0dc7c645`.
URL: https://builtwatch.org/

AWS account API/worker and cost monitor deployed. 97 Python and 13 JavaScript/runtime
tests pass. Live Lambda verification confirmed owner dashboard access, non-owner denial,
bulk import, all-profile validation before writes, and no automatic model jobs on import.
The temporary verification workspace was removed. Public HTTP checks verified updated
HTML, scripts, CSS and offline demo (200), plus anonymous workspace/admin denial (401).
Python urllib encountered an edge rejection; curl worked without authentication. No
browser visual QA or new paid model assessment was performed for this release.

SNS subscription confirmation remains **pending** as of deployment. The user explicitly
approved the recipient and cost-monitor/budget setup. They must click AWS's subscription
confirmation email before warnings can be delivered. Cost monitor's cached invocation
can refresh confirmation without another Cost Explorer call. Do not create a duplicate
subscription. The CAD 25 monthly target is not an exact provider invoice cap.

## Final independent-registration release complete

Sites version 6 is live at https://builtwatch.org/ . Deployment appgdep_6aa0fe3e56208191b76c1649f00a96c8 succeeded with environment revision 3; deployed source b22ceb9f09041f71abe622b79b3509e83c6b758e. It includes the tested connection-renewal fix. No release work or approval remains pending from this request. Independent email sign-in replaces ChatGPT authentication; returning owner must register and verify their configured email to access preserved inventory.

All prior live sign-in, isolation, registration/revocation/logout tests passed. Final session endpoint returned anonymous JSON 200; offline demo is served separately. 89 Python and 11 Node tests pass. Current temporary test accounts were cleaned up. Keep the scoped credentials private. There is no promise of a hard total AWS bill cap or immunity from hosting outages; local demo is independent of live ceilings and the downloadable standalone copy runs offline. Read ACCOUNTS.md for user instructions and controls, SECURITY.md for the bounded audit results. Earlier pending-release notes are historical.

## Independent registration deployed and verified — 9 September 2026

Sites version 5 deployed successfully with environment revision 3: appgdep_6aa0d72faae081919791e0bb5de5adfe, source d29d0a5af4be4aefd5a007c4ef478fcc2edb624d. Public URL unchanged. Live HTTP tests verified anonymous access, independent Cognito sign-in with a secure cookie, isolated AWS workspace, scoped agent registration, revocation, logout and the standalone offline download. The synthetic Cognito/AWS account was deleted and its live D1 session/connection revoked; private data/auth-test.json removed. No test model calls or emails were sent.

89 Python and 11 Node/runtime tests passed. The five inline offline scripts pass syntax checks. Python and production npm dependency audits found no known vulnerabilities. Existing BuiltWatch AWS budget remains $20/month; both current and retired URLs verified AWS_IAM. No independent penetration or visual/mobile browser audit is claimed. Email inbox delivery remains for the registering user to verify.

Final small correction: renewing a still-existing agent connection preserves its app ID instead of creating a duplicate app. Its regression test also verifies the old token stops working. This correction requires the next saved release; all earlier readiness/approval-pending notes below are historical. User explicitly reauthorized continuing and automatic approvals. No extra deployment approval is needed.

## Independent email registration release — ready for deployment

The user requested independent registration, interactive anonymous demo that survives live ceilings, revocable daily agent integration, security review, and public deployment. This supersedes the earlier ChatGPT sign-in decision. Cognito Lite pool and confidential app client are provisioned; credentials and verified-owner mapping are stored in Sites environment revision 3. Never print private data/* settings.

Implemented email/password signup, verification/resend/recovery, hashed seven-day sessions, one revocable 90-day single-app agent connection with one sync per UTC day, local interactive demo and offline download. Static demo precedes every API/identity/allowance path. Owner email verification maps to the preserved tenant. AWS sync backend is deployed; IAM-only URLs remain protected. See ACCOUNTS.md and SECURITY.md for authoritative current design.

89 Python and 11 Node/runtime tests passed, including mocked Cognito lifecycle, quota, cookie, revocation and no-network demo tests. A real synthetic Cognito account successfully signed in through the actual Worker runtime, accessed an empty isolated AWS workspace, registered one app through agent sync, revoked its token and signed out without model calls. No verification email was sent during that synthetic test; actual inbox delivery requires the registering user's verification. Temporary test account remains in data/auth-test.json pending live-site verification and cleanup. Audit inspected 155 historical Git blobs and current source; no deployment credential/key matches. Production npm dependency audit has no advisories.

Next: save/deploy this exact source publicly with D1 migration, verify actual cookie sign-in on live site and anonymous demo assets, delete synthetic Cognito/AWS/D1 records, record deployment completion. Public access and AWS registration provisioning are already authorized. Do not ask again.

## Public pilot live — 9 September 2026

Release completed at https://builtwatch.org/ . Sites version 4, source cc5928c4106f5a16739575cf1b098f24fc5546ed; deployment appgdep_6aa0b602c5748191ac1f416cd9c33b48 succeeded with environment revision 2. Public access revision 2 applied with explicit user authorization.

Both current and retired Lambda URLs now require AWS IAM. Anonymous direct requests returned 403; the production gateway code running in the actual Worker runtime returned 200 with its invoke-only credentials after protection. Public page and updated assets returned 200; forged client identity remained signed_in=false and workspace API returned 401. The D1 migration was included in the successful release. A second real-user sign-in and visual/mobile acceptance remain unverified; no independent security audit is claimed.

The live corrected Nova Lite intake test captured Gmail, left jurisdiction unknown, kept the draft unsaved until confirmation, and saved successfully after confirmation. Estimated cost $0.00010908. Temporary intake and gateway test workspaces were removed; shared model charges retained. 88 Python and seven Node/runtime tests passed. IAM credentials remain only in private operator settings and Sites secrets. The owner inventory and new daily schedule remain; legacy daily schedule stays disabled.

All older approval-pending and release-pending text below is historical and superseded by this entry. No further public or IAM identity approval is needed for this completed release. Avoid rolling back to version 3 without adapting its gateway: that version cannot sign AWS IAM requests.

## Agent-led intake and protected public pilot — release verification

The user approved public deployment, the scoped IAM gateway identity, and continuing without repeated permission questions. Older pending-approval notes below are historical and superseded.

Implemented: description/README/builder-summary intake using Strands Nova Lite, review before saving, summary-based updates, copyable builder-agent findings, 25-workspace admission, five drafts/day, shared request counters, and AWS SigV4 gateway authentication. AWS remains the main application platform; Sites supplies the UI and ChatGPT sign-in. See PUBLIC_LAUNCH.md and ACCOUNTS.md.

88 Python and seven Node/runtime tests passed. Scoped gateway credentials were provisioned and stored as Sites secrets. A real gateway request to AWS succeeded. A live intake test exposed an omitted named service; extraction schema descriptions were strengthened and are being verified before release. The original owner enrollment is preserved. Final release work: finish live extraction check, publish the new UI and D1 migration privately, enable IAM-only URLs, verify, then apply already-authorized public access. Do not claim that these final steps are done until verified.

## Legacy schedule retired with user approval

The user explicitly approved turning off the old schedule. AWS read-back verified `builtwatch-workspace-daily` DISABLED and `builtwatch-accounts-daily` ENABLED. Original S3 data is preserved. Only public Site access remains pending approval; subsequent historical notes describing both schedules as active are superseded.

## Owner sign-in and inventory migration verified

The user confirmed the fixed site opens their private workspace. While Sites remained owner-only, exactly one account had verified HMAC requests after the fixed deployment; this matched the user's real sign-in, with no competing automated identity requests in that interval. Copied the legacy owner data into that account: 1 system, 22 snapshots, 2 runs, 11 findings, 0 dispositions; assessment cache and cost ledger also retained. Read-back counts verified; model ledger total $0.1202207. Original S3 database remains untouched. The target partition has a `legacy-migration` marker.

**Pending approvals:** public Site access (asked, no answer yet); disabling the legacy `builtwatch-workspace-daily` schedule (asked after verified migration, no answer yet). Automatic approval review rejected combining migration with retiring the legacy schedule, so the approved safer migration retained the old schedule. The new `builtwatch-accounts-daily` schedule is enabled. Do not silently disable the old one or change Site access. The code/account upgrade and real owner sign-in are working; broader-user acceptance remains pending wider access and a second account.

## Latest verification and connection fix

The account site is deployed at the existing URL. The first account release failed at the gateway because the Sites Cloudflare runtime rejects fetch `redirect: "error"`. Fixed with `redirect: "manual"` and explicit rejection of 3xx responses; do not revert to `error` even if Node tests or current web docs accept it. `npm test` now includes an actual Miniflare runtime test. It requires local loopback-port permission in sandboxed environments.

81 Python tests and 5 JavaScript/runtime tests pass. A real AWS background scan completed across all 11 sources for $0.05344974, while workspace GET remained available. A live header-spoofing check confirmed Sites strips client-supplied identity headers. The supported Sites bypass token does not supply a signed-in user; it cannot establish the owner's migration identity.

Connection fix source: `1374554e81c9c0cef2ed0314fd6cbeb6a0bb7d9c`, saved Sites version 3. Deployment succeeded 2026-09-08 12:50 UTC. Public-access approval remains pending. The user was asked to refresh after reporting the initial connection failure. Do not claim confirmed browser sign-in success until the user verifies it. Legacy owner S3 inventory is retained, not yet assigned to a new account.

# Separate-account upgrade — 8 September 2026

Current work replaces the shared-key web workspace with Sites ChatGPT sign-in and account-partitioned DynamoDB. See [ACCOUNTS.md](ACCOUNTS.md) for user steps, security boundaries, deployment and limitations. The previous owner database remains in S3. The site access policy is still owner-only unless explicitly changed after user approval.

New code: `server/worker.mjs`, `builtwatch/accounts.py`, `builtwatch/dynamo_store.py`, `infra/accounts_runner.py`, `infra/deploy_accounts.py`. Runtime settings: Sites `BW_API_URL` and secret `BW_PROXY_SECRET`. New AWS resources: `builtwatch-accounts`, `builtwatch-accounts-api`, `builtwatch-accounts-worker`, `builtwatch-accounts-daily`.

Validation: 81 offline Python tests cover both SQLite and DynamoDB implementations; four Worker boundary tests cover anonymous access, CSRF, server-derived account signatures and upstream failures. Browser UI/sign-in with a second real account has not been tested.

---

Earlier release notes follow (historical, not the current account architecture).

# Current web release — 8 September 2026

The previous CLI-only handoff below is retained as historical context. Its "not done"
list and zero-cost claims are superseded by this section and ARCHITECTURE.md.

- Added a responsive, accessible static web workspace in `web/`, hosted with Sites.
- Added an owner-key authenticated API (`web_api.py`, `infra/web_runner.py`).
- Deployment script: `infra/deploy_web.py`. Uses private encrypted S3 checkpoints and
  Lambda reserved concurrency 1. Do not increase concurrency without redesigning storage.
- Owner key and access instructions are gitignored under `data/`. Never publish them.
- Public sample is a sanitized export of three example profiles and real replay results.
- Daily checks at 7 a.m. Toronto; $10/month estimated model threshold.
- Fixed per-profile assessment caching, incomplete-assessment retries, and reopening
  materially changed findings. Added page-difference context; semantic precision remains
  a model limitation.
- README and cost documentation now distinguish metered model thresholds from hard
  account caps and describe actual hosting costs and single-owner limitations.

## Historical handoff

# BuiltWatch handoff

Everything needed to continue this work from a cold start, with no access to the
conversation that produced it. Written to be tool-agnostic — follow it whether you are a
person or another coding agent.

**Last updated:** 8 September 2026, after the second full real-model run.

---

## 1. Read these first, in this order

| Document | Why |
|---|---|
| [README.md](../README.md) | What the product is and what it refuses to do |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Why it is shaped this way; diagrams; module map |
| [../AGENTS.md](../AGENTS.md) | **The seven invariants.** Do not change code that weakens one. |
| [PRECISION.md](PRECISION.md) | Measured quality, including where it fails |
| [COST_CONTROLS.md](COST_CONTROLS.md) | Spend ceilings and abuse resistance |
| [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) | Hackathon requirements and open blockers |
| [ISSUES.md](ISSUES.md) | **Open defects.** Read before changing anything. |
| [DEPLOY.md](DEPLOY.md) | Deploy + re-scan runbook, verified end to end |

If you read only one, read `AGENTS.md`. The invariants *are* the product.

---

## 2. Environment — exact reproduction

The system Python on the original machine is 3.9.6 and **cannot run this project**;
Strands requires >= 3.10.

```bash
# Python 3.12 via uv (installs to ~/.local/bin, no sudo)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.12

cd builtwatch
uv venv --python 3.12
uv pip install -e ".[dev]"

.venv/bin/python -m pytest -q      # expect: 44 passed
.venv/bin/python -m ruff check src tests infra   # expect: All checks passed!
```

Tests make **no AWS calls** and cost nothing. Run them before and after every change.

---

## 3. AWS access

**Account `[aws-account-redacted]`** (`lingac2233`). This is a deliberate move from an earlier
account (`561217459367`) — do not use the old one, nothing is provisioned there any more
except an orphaned budget.

Access is via AWS IAM Identity Center, already configured in `~/.aws/config` as profile
`[aws-profile-redacted]` (AdministratorAccess).

```bash
aws sso login --profile [aws-profile-redacted]    # token expires; re-run when it does
export AWS_PROFILE=[aws-profile-redacted]
export AWS_REGION=us-east-1
```

The token expires every few hours. The symptom is
`TokenRetrievalError: Token has expired and refresh failed` — just log in again.
`aws sso login --no-browser` prints a device code if the browser cannot be opened
automatically.

### Model configuration — read this before you debug a ValidationException

**Anthropic models are NOT entitled on this account.** Any invocation returns:

```
ValidationException: Error 002: Access to Bedrock models is not allowed for this account
```

This is not IAM. The account never submitted Bedrock's one-time use-case form, so
`agreementAvailability = NOT_AVAILABLE` for Anthropic while `authorizationStatus` and
`entitlementAvailability` are both fine. Fixing it requires a console action by the
account owner (it is an acceptance of model provider terms) — see
`SUBMISSION_CHECKLIST.md`.

Amazon Nova works. Use:

```bash
export BW_SCREEN_MODEL=us.amazon.nova-lite-v1:0
export BW_ASSESS_MODEL=us.amazon.nova-pro-v1:0
```

**Always confirm with `builtwatch doctor` rather than assuming.** It probes each model in
the preference ladder with a real one-token invocation and prints the cheapest working
pair plus the exact exports. Bedrock's control plane happily lists 122 models the account
cannot invoke, so `ListFoundationModels` is worthless as an availability check.

If Anthropic access is granted later, `doctor` will pick it up automatically and quality
should improve — see "Known weaknesses" below.

---

## 4. Run it

```bash
export AWS_PROFILE=[aws-profile-redacted] AWS_REGION=us-east-1
export BW_SCREEN_MODEL=us.amazon.nova-lite-v1:0 BW_ASSESS_MODEL=us.amazon.nova-pro-v1:0
export BW_DB=data/builtwatch.db

.venv/bin/builtwatch source list                 # exactly what is watched — free
.venv/bin/builtwatch system import examples/passports/inbox-triage.json
.venv/bin/builtwatch system import examples/passports/recipe-site.json
.venv/bin/builtwatch system import examples/passports/support-widget.json

.venv/bin/builtwatch scan --mode replay          # ~4 min, ~$0.25, 33 pairs
.venv/bin/builtwatch scan --mode replay          # again: 0 findings, $0.0000
.venv/bin/builtwatch finding list
.venv/bin/builtwatch finding export <id> --out handoff.md
.venv/bin/builtwatch status                      # spend against ceilings
```

`--mode replay` uses the committed corpus in `replay/` (real material captured from the
registry sources, dated). `--mode live` fetches for real. Refresh the corpus with
`python scripts/capture_replay.py`.

### Cost discipline while developing

Budget is **$20/month, owner-approved**, with an AWS budget alarm at
50/80/100%. Spend to date is roughly **$0.51**.

- A full 3-system x 11-source scan costs **~$0.25** and takes ~4 minutes.
- A repeat scan with nothing changed costs **exactly $0.00** — no source changed, so no
  model is invoked.
- Scope experiments: `BW_MAX_SOURCES=2 builtwatch scan --system inbox-triage` (~$0.017).
- Never widen a ceiling to make something pass. Fix what overran.

---

## 5. Current state

### Done and verified against real models

- System passports from plain text (Strands extraction) and neutral JSON import.
- Curated 11-source registry across all seven categories; real captured replay corpus.
- Hardened fetcher: HTTPS-only, public-IP-only, no cross-host redirects, streaming size
  caps. All 11 sources fetch successfully.
- Two-stage pipeline: Nova Lite screen -> Nova Pro assessment with four read-only Strands
  tools, `BudgetGuard` hooks enforcing ceilings.
- Grounding validation that rejects fabricated quotes and non-existent passport facts.
- Dedup, dispositions, Markdown/JSON export, full CLI, 44 offline tests.
- Lambda + EventBridge Scheduler deploy script with least-privilege IAM (**written, not
  yet executed**).

### Not done

| Item | Notes |
|---|---|
| **Web UI** | **Does not exist.** CLI only. See section 7. |
| Lambda actually deployed | `infra/deploy_lambda.py` is written but has never been run |
| AgentCore Runtime | Control plane verified reachable; nothing deployed |
| Repo public | **Required before submission** — currently private |
| Demo video | Beat sheet in `SUBMISSION_CHECKLIST.md`; owner must record |
| Domain | `builtwatch.org` / `.com` / `.io` / `.dev` all unregistered, none purchased |

---

## 6. Known weaknesses — do not rediscover these

1. **Standing policy slips through as `relevant`.** The Anthropic AUP is flagged for
   `inbox-triage` even though nothing about it changed. The materiality bar catches "new
   model released" but not "this rule already applied yesterday". **The right fix is
   diffing against the previous snapshot** rather than assessing the current document
   whole. This is the highest-value quality improvement available.
2. **Nova Pro fabricates quotes** — 2 in 57 assessments. The validator catches them, but
   reaching a downgraded answer still costs money. Anthropic entitlement would likely
   help; untested.
3. **Review suggestions are generic.** "Review the policy to ensure compliance" is not
   worth a person's attention. Needs richer passports than the three examples carry.

### Traps that already cost time — do not repeat

- **`Agent.structured_output()` fires no hooks and reports zero usage.** It is deprecated.
  Every call site must construct the agent with `structured_output_model=` and call the
  agent, then read `result.structured_output`. Getting this wrong made the entire budget
  guard silently inert while scans reported `$0.0000` and really spent money.
- **`AfterModelCallEvent` carries no token counts.** Usage comes from the agent's
  `event_loop_metrics.accumulated_usage`, read as a delta.
- **My fetcher does not follow redirects on purpose.** Several registry URLs needed their
  final destination resolved by hand. A `301` in `source_health` means update the registry
  URL, not fix the fetcher.
- **Lambda `/tmp` does not persist.** A cold database makes every finding look new. The
  runner warns; a real deployment needs EFS or the DynamoDB backend.

---

## 7. If you are asked to build the web UI

None exists. What it needs, roughly in value order:

1. **Read-only findings view** — list findings by system, show evidence, facts,
   inferences, unknowns, and the coverage-failure banner. This is most of the demo value.
2. **Disposition actions** — acknowledge / dismiss with reason / export.
3. **Passport intake form** — plain text in, extracted passport shown for confirmation.

Constraints that are not negotiable:

- **`BW_DEMO_MODE=1` must gate everything public.** Read-only replay, no live fetch, no
  system creation, no path by which an anonymous visitor can cause a model call. There is
  currently no authenticated endpoint that spends money, and it must stay that way.
- Idle cost must remain **$0**. A static front end against a small read API, or a
  pre-rendered snapshot of a scan, both satisfy this. A always-on server does not.
- The store interface in `store.py` is deliberately narrow so a DynamoDB backend can drop
  in without touching the pipeline.

---

## 8. Hackathon context

Agents for Humans, **Professional Agents** track. Submission closes **14 September 2026,
17:00 PT**. Judging 15 Sep – 8 Oct.

Hard requirements: Strands Agents SDK (satisfied), AWS account (satisfied), **public repo
with an OSI license** (MIT license present, **repo still private**), README (present),
architecture diagram (present), demo video <= 5 min (not recorded), AWS Builder ID
(obtained).

Judged equally on Technical Implementation, Design, Potential Impact, Creativity &
Originality, and Presentation. A live demo or AgentCore deployment strengthens the first.

Rules require the project be newly created during the submission period. First commit is
8 September 2026 and no pre-existing code was incorporated. AI assistance is disclosed in
`NOTICE`; keep that accurate — if another tool contributes, add it there.

## September 9 update — quality, bulk import and cost guard

New implementation: exact passage selection IDs; named vendor/product relevance gates;
legacy invalid findings withheld behind friendly quality notices; multi-app JSON preview
and import; responsive animated watch flow; owner-only cached cost and utilization portal.
Shared model reservations reduced to USD 5. AWS daily account-cost monitor and SNS email
subscription were explicitly approved by the user, including the recipient and lowering
BuiltWatch's existing AWS budget to USD 12. Paid model work stops at reported USD 10 or
stale/failed billing status. CAD 25 is a monthly target, not an exact total invoice cap.
Do not claim email delivery is enabled until the SNS subscription is confirmed.
See COST_CONTROLS.md for current settings; older limits above are historical.
