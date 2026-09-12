# BuiltWatch open issues

Machine-readable issue register for whoever continues this work. Generated 10 September
2026 from a full review, and updated the same day as items were closed of the working tree, the test suite, and live AWS state.

**Read [HANDOFF.md](HANDOFF.md) first** for environment setup and AWS access, and
[DEPLOY.md](DEPLOY.md) for the deploy + re-scan runbook. This file
lists only what is *wrong*, not how the system works.

Deadline context: hackathon submission closes **14 September 2026, 17:00 PT**.

Severity: `BLOCKER` submission fails without it · `HIGH` damages credibility or costs money
· `MED` real defect, bounded impact · `LOW` hygiene.

Ownership: `AGENT` an agent can complete it · `HUMAN` requires account/console/inbox access
no agent has.

---

## BW-1 · Grounding validator does not check that a cited fact *supports* the claim
**Severity:** HIGH · **Owner:** AGENT · **Status:** ✅ FIXED AND LIVE 10 Sep 2026 — deployed and verified by re-scan; `CVE-2026-85880` absent from both tenants, no relevant finding carries a fabricated dependency

**Evidence.** A finding published 2026-09-09T06:51Z against the `BuiltWatch` passport
(`technologies: ['Strands Agents','AWS SDK','Cloudflare Workers']`):

- title: `New Microsoft Windows vulnerability (CVE-2026-85880)`
- relevance: `relevant`
- cited system fact: `services[0] = "CISA Known Exploited Vulnerabilities (KEV)"`
- inference: `"The system uses Microsoft Windows, which now has a known vulnerability."`

Nothing in that passport mentions Windows. The inference is invented.

**Why it passed.** `Finding.validate_grounding()` in `src/builtwatch/models.py` checks only
that (a) the evidence passage is verbatim and (b) the cited `system_facts` key exists with
a matching value. Both held. It never checks whether the cited fact *supports* the claim,
and it never checks inferences against the passport at all. The model cited a source the
system *monitors* as though it were a technology the system *uses*.

**Contributing cause.** `SystemPassport.services[]` is overloaded. It holds both "vendors I
depend on" and "sources I watch". For this passport those are the same strings, which is
what made the confusion available.

**Current mitigation.** `src/builtwatch/quality.py::dependency_mismatch()` (commit
`7453039`) suppresses a named-product vulnerability when the product is absent from
`technologies + services`. Verified: it returns `True` for this exact case, so a fresh scan
suppresses it.

**Why it is not closed.** `PRODUCTS` is a hardcoded 7-entry allowlist (windows, exchange
server, sharepoint, fortinet, citrix, vmware, cisco). Probed against the same passport,
all of these still pass through unsuppressed:

| Probe text | `dependency_mismatch` |
|---|---|
| `Critical Linux kernel privilege escalation` | `False` |
| `OpenSSL heap overflow CVE` | `False` |
| `Apache Log4j RCE` | `False` |
| `Kubernetes API server flaw` | `False` |
| `nginx buffer overflow` | `False` |

It patches the observed symptom, not the class of defect.

**Suggested fix.**
1. Extend `validate_grounding()` so an `inference` naming a technology or product absent
   from `passport.fact_index()` downgrades the finding to `insufficient_information` and
   records the reason in `unknowns`. This is model-agnostic and needs no allowlist.
2. Split `SystemPassport.services` into `depends_on[]` and `monitors[]`, and forbid
   `monitors[]` entries from being cited as `system_facts` for a relevance claim.
3. Keep `dependency_mismatch()` as defence in depth.

**Verify with.** A regression test asserting the BuiltWatch passport + the CVE-2026-85880
passage yields `insufficient_information`, plus the five probes above.

---

## BW-2 · A retracted finding is never withdrawn
**Severity:** HIGH · **Owner:** AGENT · **Status:** ✅ FIXED AND LIVE 10 Sep 2026 — deployed; all 43 generation-0 findings withheld and regenerated (8 and 7 current-generation findings per tenant)

The BW-1 finding is still stored as `relevance: relevant` in DynamoDB and still appears in
"Needs attention", even though current code would suppress it. Fixing the code did not
retract what it had already published.

There is no mechanism to withdraw a finding that a later, better assessment would not have
made. `assessed(pair_key)` (keyed on system + profile hash + mode + source + content hash)
actively *prevents* re-assessment while the source is unchanged, so the stale row persists
indefinitely.

**Suggested fix.** Add a `quality_version` constant. Include it in `pair_key` so a bump
invalidates the assessment cache, and mark findings from an older `quality_version` as
superseded rather than serving them. Then bump it as part of the BW-1 fix.

**Interim action.** The two live tenants' findings need purging or re-assessing before any
demo or judging. Tenants: `8ae7e086b71e...` (21 findings, 3 relevant) and
`e4e140e3b676...` (22 findings, 1 relevant).

---

## BW-3 · Repository is private
**Severity:** BLOCKER · **Owner:** HUMAN · **Status:** open

`GET api.github.com/repos/kelvin-ling/builtwatch` → `404`. Contest rules require a public
repository under an OSI licence. MIT licence and NOTICE are present and correct; only
visibility is wrong.

**Action.** GitHub → Settings → General → Danger Zone → Change visibility → Public. No
agent has GitHub API access here (SSH push works; the REST API does not).

---

## BW-4 · `docs/SUBMISSION_CHECKLIST.md` states facts that are false
**Severity:** HIGH · **Owner:** AGENT · **Status:** ✅ FIXED 10 Sep 2026 — every row re-verified against live state; Bedrock section and video beat sheet rewritten

This document is intended to drive the Devpost submission form, so its errors propagate
into the actual entry.

| Line | Claims | Reality |
|---|---|---|
| AWS account | `561217459367` | Everything runs in `[aws-account-redacted]`. The old account holds only an orphaned budget. |
| Functioning agent | "Real-model path blocked on Bedrock access" | False. Amazon Nova has run in production for days; two tenants have completed scans. |
| Live demo link | "⬜ Optional, unregistered" | A live site exists and returns 200. |

**Action.** Rewrite against verified state before anything is submitted.

---

## BW-5 · Public demo is served from a ChatGPT-branded domain
**Severity:** HIGH · **Owner:** HUMAN (decision) + AGENT (implementation) · **Status:** open

Live URL is `https://builtwatch.org` (verified 200). This is the demo
link an AWS-competition judge would open. `.openai/hosting.json` also binds a Cloudflare
D1 database.

The AWS-native substance is real and substantial — Strands, Bedrock, Lambda, DynamoDB,
Cognito, EventBridge Scheduler, S3 — but the front door does not communicate it.

`builtwatch.org`, `.com`, `.io`, `.dev`, `.app` and `.net` were all unregistered as of
8 September 2026. `docs/CUSTOM_DOMAIN.md` exists; a domain purchase requires a human.

---

## BW-6 · Operational cost warnings are not being delivered
**Severity:** MED · **Owner:** HUMAN · **Status:** open — confirmation re-sent 10 Sep 2026

*Corrected 10 Sep: an earlier revision of this file called cost alerting "dead". That was
wrong and overstated the risk. Budget alerts work. Only the SNS channel is unconfirmed.*

Two independent alerting paths exist. One works, one does not:

| Path | Destination | Needs opt-in? | Status |
|---|---|---|---|
| **AWS Budgets** — 50% / 80% / 100% of `builtwatch-monthly-20usd` | `[owner-email-redacted]` | No | ✅ **Working** |
| **SNS** `builtwatch-owner-cost-alerts` — operational warnings from the daily monitor | `[owner-email-redacted]` | Yes | ❌ `PendingConfirmation` |

So spend threshold alerts are being delivered. What is *not* delivered is the daily
monitor's richer operational warnings — unusual-spend detection, "approaching allowance",
"paid checks paused", "shared reserve nearly used".

**Action.** The confirmation email was re-sent on 10 Sep 2026 to `[owner-email-redacted]`
(subject: *AWS Notification - Subscription Confirmation*). Click the link in it. Only the
mailbox owner can do this. Verify with:

```bash
aws sns list-subscriptions-by-topic --topic-arn \
  arn:aws:sns:us-east-1:[aws-account-redacted]:builtwatch-owner-cost-alerts
```

`SubscriptionArn` will change from `PendingConfirmation` to a real ARN, and the monitor's
`email_confirmed` flag flips true on its next daily run.

**Note two budget facts worth knowing.** The budget is now **$12**, not the $20 originally
set — `deploy_cost_monitor.py` lowered it. And a separate `Monthly EC2 Budget`, also $12,
exists in the account and is unrelated to BuiltWatch; do not read its alerts as this
project's spend.

**Spend controls themselves are healthy and fail closed**: month-to-date Cost Explorer
`$0.00`, internal ledger `allocated $0.5399`, `GLOBAL_MONTH_LIMIT $5.00`, `RESERVATION
$1.00` reserved then settled atomically, paid checks pause at `$10` reported cost or on any
billing-query failure.

---

## BW-7 · `admit()` can raise from its `finally` block
**Severity:** MED · **Owner:** AGENT · **Status:** ✅ FIXED 10 Sep 2026 — lock release suppressed, regression test added

`src/builtwatch/admission.py::admit()` releases its enrollment lock inside `finally` with
`ConditionExpression="nonce = :n"`. The lock's TTL is 10 seconds. If the DynamoDB query
takes longer and another invocation claims the lock, the nonce no longer matches,
`delete_item` raises `ConditionalCheckFailedException` from the `finally` block, and that
exception replaces the function's return value — surfacing as a 500 in the signup path.

**Suggested fix.** Wrap the release in `contextlib.suppress(ClientError)`, or narrow it to
suppress only `ConditionalCheckFailedException`.

---

## BW-8 · Lint gate not run on new infra code
**Severity:** LOW · **Owner:** AGENT · **Status:** ✅ FIXED 10 Sep 2026 — infra lint clean; equivalence of reflowed deploy scripts verified by AST + literal diff

`ruff check src tests infra` reports **33 errors**, all confined to five files added in the
account/cost work: `infra/cost_monitor.py`, `infra/deploy_accounts.py`,
`infra/deploy_auth.py`, `infra/accounts_runner.py`, `infra/deploy_cost_monitor.py`.

Style only — line length, import ordering, blind `except Exception`, magic values. No
correctness impact. 6 are auto-fixable. Everything under `src/` and `tests/` is clean.

---

## BW-9 · Orphaned single-tenant stack still deployed
**Severity:** LOW · **Owner:** AGENT · **Status:** open

Superseded by the multi-tenant accounts stack but still present:

- Lambda `builtwatch-workspace` (600s, reserved concurrency 1) — **function URL still live**
- S3 `builtwatch-workspace-[aws-account-redacted]` (`workspace.db`, 282 KB)
- EventBridge schedule `builtwatch-workspace-daily` — already `DISABLED`

Near-zero cost, but it is a live endpoint outside the current design and it confuses the
architecture story. Confirm the data is migrated, then delete.

---

## BW-10 · `insufficient_information` rate is 27%
**Severity:** MED · **Owner:** AGENT · **Status:** open, needs judgement

11 of 42 stored assessments across the two live tenants resolve to
`insufficient_information`. Refusing to conclude is by design and better than guessing —
but at this rate it reads as evasion rather than rigour, and it costs a full assessment
each time.

Worth sampling to distinguish genuinely undeterminable applicability from prompt or
passport weakness before changing anything.

**Measured after the 10 Sep re-scan: 2 of 15, or 13%** — down from 27%, and the earlier
prediction that BW-1 might push it up was wrong. One tenant returned none at all. The
remaining two are on a single tenant and worth reading before any further change.

Original note follows.

**Do this after the deploy and re-scan, not before.** All 43 stored findings are from
assessment generation 0 and will be regenerated under the BW-1 rules. Sampling now would
analyse a population that is about to be replaced — and since BW-1 converts some
over-confident `relevant` verdicts into honest `insufficient_information`, the rate may
legitimately *rise* before it falls. Measure against the new generation.

---

## BW-11 · `is_disposed()` is dead code
**Severity:** LOW · **Owner:** AGENT · **Status:** ✅ RESOLVED 10 Sep 2026 — as a decision, not a code change

The question was whether to wire it back into the pipeline or delete it. **Neither: it
stays, unused, and that is correct.**

Suppression is keyed on `revision_hash`, not on disposition, and that is the behaviour you
want. A development you dismissed stays quiet while its substance is unchanged, but if the
source is *materially* revised — a proposal becomes law, a deadline moves, scope widens —
you are told again. Keying suppression on disposition would silence that permanently, so a
single dismissal would hide every future change to the same rule.

`is_disposed()` remains as a reporting helper. Both implementations now carry a docstring
saying it must not be used for suppression, and
`test_disposition_does_not_permanently_silence_a_development` pins the behaviour so nobody
"fixes" it by wiring it in.

---

## BW-12 · Frontend deployment gap
**Severity:** MED · **Owner:** AGENT (with Sites access) · **Status:** ✅ FIXED AND LIVE 10 Sep 2026 — categorized sources and the modal scroll/footer correction shipped in Sites version 21

The categorized **Watched sources** view and modal footer fix are now live. The AWS
backend and frontend still deploy through different paths:

| Layer | Deploys via | Available here? |
|---|---|---|
| Lambda / DynamoDB / EventBridge | `infra/deploy_accounts.py` | ✅ yes |
| Static site + Cloudflare Worker + D1 | ChatGPT Sites (`.openai/hosting.json`, project `appgprj_6a9fa334…`) | ✅ through an agent with Sites access |

The Worker's runtime secrets (`BW_PROXY_SECRET`, the scoped AWS keys, the Cognito client
secret, and the private owner migration mapping) remain in Sites, not in this repository.

Sites version 21 deployed source `0fce94466a0756fe7e5114933c263a79be5f4d01` and uses
the refreshed `?v=20` browser asset key. Live HTTP verification found the categorized
source groups, category-level failure counts, and separated modal action footer in the
served assets.

---

## BW-13 · `www.builtwatch.org` does not resolve
**Severity:** MED · **Owner:** HUMAN (Cloudflare DNS) · **Status:** open

`builtwatch.org` serves 200 and resolves to `172.64.80.1` (Cloudflare). `www.builtwatch.org`
has **no DNS records at all** and fails to connect — `curl` returns `000`, not a redirect.

Anyone who types or is handed the `www` form gets a connection failure rather than the site.
For a submission where judges are given a link, that is a needless way to lose them.

**Fix:** in Cloudflare DNS for `builtwatch.org`, add a proxied `CNAME` `www` → `builtwatch.org`,
then a redirect rule sending `www` to the apex so one canonical host wins. No agent here has
Cloudflare access for this zone.

---

## BW-14 · The old host still serves a full copy of the site
**Severity:** MED · **Owner:** AGENT (with Sites access) · **Status:** ✅ FIXED IN SOURCE — pending next Sites deployment

The Worker now redirects `https://builtwatch.kelvinlingac.chatgpt.site` to the canonical
`https://builtwatch.org`, preserving paths and query strings. The same release adds
`robots.txt` and a canonical link in the HTML. The redirect is not live until the next
Sites deployment completes.

Before this fix, three consequences mattered:

1. A judge handed the ChatGPT-branded URL sees an AWS-competition entry hosted on a
   ChatGPT domain. BW-5 was closed on the basis that `builtwatch.org` is now primary; it
   is only actually primary once the old host stops answering.
2. The two copies drift. The old host is a separate deployment and will keep serving
   whatever it last received.
3. Duplicate content across two hosts, with no `rel=canonical` on either.

**Fix:** complete the next Sites deployment and verify the old host returns a 301.
The implementation is covered by a Worker regression test.

Related and cheap while there: `https://builtwatch.org/robots.txt` now disallows only
`/api/`, and `<link rel="canonical">` points at the apex.

---

## Not broken — verified working

Recorded so nobody re-investigates these.

- **147 tests pass**. Ruff still reports 13 inherited style findings in account/edge code
  and one existing asset-test line; no new production behavior is blocked by them.
- **Multi-tenant path completes end to end.** Both tenants show `job=complete`.
- **Invariant 1 holds in production.** A real Gmail fetch `ReadTimeout` on 2026-09-09 was
  recorded as `coverage failure on gmail-sender-guidelines: network_error`, not silence.
- **Budget reservation is atomic and fails closed** — conditional DynamoDB updates, stale
  cost data pauses paid checks.
- **Function URLs are `AWS_IAM`**, reached through a SigV4-signing edge proxy
  (`infra/protect_api.py`), not anonymous.
- **Admission control is bounded**: 25 workspaces, 300 requests/tenant/day, 100 lifetime
  registration attempts, Cognito email verification required.

---

## Environment gotcha

Two SSO token caches exist under `~/.aws/sso/cache/`. The AWS CLI resolves the valid one;
**boto3 picks the expired one** and fails with
`TokenRetrievalError: Token has expired and refresh failed`.

Prefix Python/boto3 work with:

```bash
export AWS_PROFILE=[aws-profile-redacted] AWS_REGION=us-east-1
eval "$(aws configure export-credentials --format env)"
```

When the underlying session expires, only a human can run
`aws sso login --profile [aws-profile-redacted]`.

---

## Remaining work, in order

The backend corrections and the pending frontend work are now live. Use
[DEPLOY.md](DEPLOY.md) only when future backend code changes require another release.

1. **BW-3** — one click, and the submission is invalid without it (HUMAN)
2. **BW-6** — one click; confirmation email re-sent 10 Sep (HUMAN)
3. **BW-14** — deploy and verify the canonical-host redirect (AGENT)
4. **BW-10** — sample only after the re-scan; see the note in that section (AGENT)
5. **BW-9** — orphaned stack; destructive, so confirm before deleting (AGENT)
6. **Demo video** — the only remaining submission artefact (HUMAN)
