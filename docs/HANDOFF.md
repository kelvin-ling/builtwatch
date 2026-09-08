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
