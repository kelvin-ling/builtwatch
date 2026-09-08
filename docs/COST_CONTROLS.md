# Cost controls and abuse resistance

Design goal: **≈ $0/month at rest, hard-capped under $20/month in the worst case, and
impossible for a stranger to run up a bill.**

## Where money can actually go

| Component | Idle cost | Notes |
|---|---|---|
| Amazon Bedrock | **$0** | Charged per token. No tokens, no charge. |
| EventBridge Scheduler | **$0** | 14M invocations/month free; we use ~30. |
| DynamoDB (on-demand) | **$0** | Charged per request; 25 GB storage free tier. |
| Lambda / AgentCore Runtime | **$0** | Charged per invocation and duration only. |
| CloudWatch Logs | **~$0** | 7-day retention, tiny volume, 5 GB/month free. |
| **Total at rest** | **$0** | Nothing polls. Nothing stays warm. |

The only variable cost is Bedrock tokens, so that is where the controls are.

## Four layers, cheapest first

**Layer 0 — content hashing.** A source that has not changed produces no model call at
all. Most sources do not change most nights. This is the single largest saving and it
costs nothing to run.

**Layer 1 — cheap screening.** Surviving pairs go to Claude Haiku with no tools and a
3,000-character excerpt. Roughly $0.002 per pair. Most pairs die here.

**Layer 2 — bounded assessment.** Only plausible pairs reach Claude Sonnet, and the
Strands agent is capped at `BW_MAX_ITERATIONS` model calls and 3× that in tool calls.
Snapshots are truncated to `BW_MAX_SNAPSHOT_CHARS` *before* they can enter a prompt.

**Layer 3 — spend ceilings that abort.** [`BudgetGuard`](../src/builtwatch/agent/guard.py)
is a Strands hook on `BeforeModelCallEvent`. It checks the running total before every
model call and raises `BudgetExceeded` when a ceiling is hit. The scan is then marked
`aborted` with a reason — it does **not** quietly return fewer findings, because a scan
that silently stopped looking is exactly the failure mode this product exists to prevent.

These are hooks rather than prompt instructions on purpose. A ceiling a model can talk its
way past is not a ceiling.

## The knobs

| Variable | Default | What it bounds |
|---|---|---|
| `BW_MAX_RUN_USD` | `0.25` | One scan |
| `BW_MAX_DAY_USD` | `1.00` | All scans in a UTC day |
| `BW_MAX_MONTH_USD` | `15.00` | All scans in a calendar month |
| `BW_MAX_SOURCES` | `12` | Sources fetched per run |
| `BW_MAX_SYSTEMS` | `25` | Systems evaluated per run |
| `BW_MAX_ITERATIONS` | `12` | Model calls per assessment |
| `BW_MAX_OUTPUT_TOKENS` | `2000` | Output tokens per call |
| `BW_MAX_SNAPSHOT_CHARS` | `24000` | Characters stored per snapshot |

Spend is tracked in the `cost_ledger` table and read back at the start of every run, so
the daily and monthly ceilings hold **across process restarts** — not just within one run.

`builtwatch status` prints spend against ceilings.

## Measured, not estimated

First full run against real models — 3 systems x 11 sources, all sources changed (a
worst case: every source is new on a first run), Nova Lite screening and Nova Pro
assessing:

```
11 source(s) checked, 11 changed, 0 failed
29 findings across 3 systems
297,283 input tokens / 20,287 output tokens
$0.2539 total, 4 minutes wall clock
```

That is the pathological case. A steady-state night changes 0-2 sources, so Layer 0
eliminates almost all of it before a single token is spent. Measured, on an immediate
re-run with nothing changed:

```
0 new finding(s)
Estimated cost $0.0000 (0 in / 0 out)
```

Not "cheap" — actually zero. No source changed, so no model was invoked at all.

## Realistic monthly cost

Nightly scan, 12 systems, 11 sources:

- Most nights, 0–2 sources change → 0–24 screens → **$0.00–$0.05/night**
- A busy night, 5 sources change and 4 pairs warrant assessment → **~$0.20**
- Typical month: **$2–5**, and the $15 in-app ceiling stops it dead well under the AWS budget.

## AWS-side backstop

A monthly cost budget is provisioned on the account:

```
Budget:  builtwatch-monthly-20usd
Limit:   $20.00 USD / month
Alerts:  50%, 80%, 100% actual; 100% forecasted → email
```

Reproduce with [`infra/budget.py`](../infra/budget.py).

> **On "hard" limits.** AWS Budgets alert; they do not stop spend by themselves. A true
> hard stop needs a **budget action** that attaches a deny policy when the threshold trips
> — effective, but it can lock the account out of Bedrock mid-demo. The in-app ceilings are
> the real enforcement here and they abort before spending; the AWS budget is the backstop
> that catches anything outside BuiltWatch. Enable a budget action only deliberately.

## Abuse resistance

The public demo is the attack surface. It is closed by construction.

**Demo mode** (`BW_DEMO_MODE=1`) is read-only:

- no live fetching — replay corpus only, so no outbound requests can be triggered;
- no system creation — so no attacker-supplied text reaches the extraction model;
- no scans that write.

**A stranger cannot cause a model call.** Every path that spends money requires either
local CLI access or authenticated write access. There is no anonymous endpoint that
invokes Bedrock.

**Retrieval cannot be aimed.** URLs come only from the committed registry. A user, a
document, or a model output cannot introduce one. Concretely:

- HTTPS only;
- the resolved IP must be public — loopback, private ranges, link-local and
  `169.254.169.254` (cloud instance metadata) are all rejected before connecting;
- cross-host redirects are not followed;
- bodies are size-capped **while streaming**, so an endless response is cut off rather
  than absorbed;
- a 20-second timeout, and a delay between fetches.

**Prompt injection cannot spend money either.** The assessment agent has four read-only
tools and no way to request another fetch, so a hostile document cannot induce a
fetch-amplification loop.

## Verifying the controls

```bash
pytest tests/test_fetch_safety.py -v     # SSRF, size caps, failure recording
pytest tests/test_pipeline.py -v         # abort-on-ceiling, no-reassess-on-unchanged
```
