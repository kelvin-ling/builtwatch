# BuiltWatch

**You keep building. BuiltWatch remembers what you built and tells you when the world changes in a way that matters.**

Built for the [Agents for Humans hackathon](https://agentsforhumans.devpost.com/) — *Professional Agents* track. Powered by [Strands Agents](https://github.com/strands-agents/sdk-python) on Amazon Bedrock.

---

## The problem

AI coding tools made it cheap to build things. They did not make it cheap to *remember* them.

An independent professional now runs a dozen small systems: an intake form that emails clients, a scraper that feeds a spreadsheet, an agent that drafts replies, an automation that charges a card. Each one quietly depends on a vendor policy, an API version, a data-handling assumption, and a regulation that was true on the day it was written.

Then the world moves. An API version is deprecated. A bulk-sender rule changes. A transparency obligation takes effect. The thing you shipped eight months ago is now wrong, and nothing tells you — because the system that broke it doesn't know you exist.

Nobody has time to read every changelog against every thing they've built. That is the recurring work BuiltWatch takes on.

## What it does

```
Something gets built  →  BuiltWatch remembers it  →  the world changes
                      →  BuiltWatch works out which systems may be affected
                      →  a person or a builder agent gets one concise, evidence-backed finding
```

Most of the time it stays quiet. That is the point.

## What it deliberately does not do

Trust in a watcher comes from what it refuses to claim.

- **It does not watch "the whole world."** It watches an explicit, committed list of sources. `builtwatch source list` prints exactly that list and nothing is implied beyond it.
- **It does not make legal or compliance determinations.** A finding is a review prompt with citations attached, never a verdict.
- **It does not change your code.** It hands off to you or to a coding agent of your choosing.
- **It does not treat silence as safety.** A source it failed to fetch is reported as a coverage failure, loudly and separately from "nothing changed."
- **It does not guess.** When an applicability fact is missing from a system's profile, it returns `insufficient_information` and names the missing fact.

## How it works

### 1. System passports

A system passport is a small, versioned profile of something you built: its purpose, the technologies and external services it depends on, the consequential actions it takes, the data categories it touches, its assumptions and constraints, and — critically — its **explicit unknowns**.

Two ways in:

```bash
# Plain text. A Strands agent extracts structure and preserves what it could not determine.
builtwatch system add "A Python bot that reads my Gmail inbox each morning, drafts replies
with Claude, and sends them through the Gmail API to clients in the UK and Germany."

# Or a neutral JSON passport, for agent-to-agent handoff.
builtwatch system import passports/inbox-triage.json
```

Extraction never fills a gap with a plausible guess. Anything it could not determine lands in `unknowns` and stays visible.

### 2. A curated source registry

`sources/registry.yaml` is the only place a fetchable URL can come from. Nothing a user types, and nothing a fetched document says, can add a URL to it. Coverage spans vendor policies, API changes and deprecations, laws and regulations, privacy and AI requirements, communications restrictions, security incidents, and standards guidance.

### 3. A two-stage relevance investigation

This is where Strands does the work, and it is split in two for a reason — cost.

**Stage 1 — screen** (Claude Haiku, no tools, high recall). For each (system, change) pair: could this plausibly matter? Most pairs die here for a fraction of a cent.

**Stage 2 — assess** (Claude Sonnet, tool-using, bounded). Survivors get a real investigation. The agent must call tools to read the passport and the evidence before it can answer:

| Tool | What it does |
|---|---|
| `get_system_passport` | The profile, plus the exact `fact_index` keys it is allowed to cite |
| `list_evidence` | Which source documents are readable this run |
| `read_evidence` | A chunk of one document, wrapped in `<evidence>` delimiters |
| `search_evidence` | Targeted passage lookup inside long documents |

Every tool is read-only. **There is no tool that fetches a URL, sends a message, writes a passport, or runs code.** The worst a hostile document can talk the agent into is reading another stored snapshot.

### 4. Grounding is verified, not trusted

The agent returns a structured `FindingDraft`. Before anything is stored, code checks it:

- every quoted passage must appear **verbatim in the stored snapshot** — this catches fabricated quotes;
- every cited system fact must exist in the passport's `fact_index` **and match its value**;
- a `relevant` verdict with no evidence or no system fact is **automatically downgraded** to `insufficient_information`, with the reason attached.

An agent that says it cited evidence is not the same as an agent that did. The difference is [`Finding.validate_grounding`](src/builtwatch/models.py) and [`_to_finding`](src/builtwatch/agent/relevance.py).

Findings keep `facts` (stated by the source), `inferences` (the agent's reasoning), and `unknowns` (not determinable) in separate fields — and a **proposed** rule is never presented as an adopted one.

### 5. Quiet on repeat

Findings are keyed by `(system_id, development_key)` and versioned by a `revision_hash` computed from the material substance. Re-running a scan over unchanged sources produces **no new notifications**. A finding you acknowledged or dismissed stays down until its substance actually changes.

### 6. Handoff

```bash
builtwatch finding export find_a1b2c3 --format markdown --out handoff.md
builtwatch finding ack find_a1b2c3
builtwatch finding dismiss find_a1b2c3 --reason "We removed that dependency in March."
```

A saved artifact, carrying its own evidence, that a person can read or a coding agent can act on.

## Interface

BuiltWatch is a **command-line tool**. There is no web UI. Everything the product does —
intake, scanning, review, disposition, export — is reachable from `builtwatch`, and the
local mode needs no AWS deployment at all.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full diagram and the deployed AWS
topology. Continuing this work? Start at [docs/HANDOFF.md](docs/HANDOFF.md).

## Quick start

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
source .venv/bin/activate

builtwatch source list                      # exactly what is watched
builtwatch system import examples/passports/inbox-triage.json
builtwatch scan --mode replay               # reproducible, free, cited historical material
builtwatch finding list
```

`--mode replay` runs against committed, dated snapshots in `replay/` — real material captured from the registry sources, clearly labelled as a replay. `--mode live` performs real HTTPS retrieval. The two are never mixed or confused: every snapshot records which it was.

## Cost and abuse resistance

BuiltWatch is designed to cost approximately nothing at rest and to be incapable of running up a surprise bill.

- **Idle cost is zero.** Nothing polls or holds a connection. The scheduler invokes a function; between invocations, no compute exists.
- **Layered ceilings** — per run, per day, per month — enforced by a Strands hook ([`BudgetGuard`](src/builtwatch/agent/guard.py)), not by prompt text. A ceiling a model can talk its way past is not a ceiling. Hitting one **aborts the run** rather than silently degrading it.
- **Bounded before it is spent**: capped model iterations, capped tool calls, capped output tokens, and snapshots truncated before they ever reach a prompt.
- **The cheap model does the volume.** Only plausible pairs reach the expensive one.
- **Fetching is hostile to misuse**: HTTPS only, registry URLs only, resolved IPs must be public (blocks SSRF against cloud metadata and private ranges), cross-host redirects not followed, and response bodies size-capped *while streaming*.
- **Public demo mode** (`BW_DEMO_MODE=1`) is read-only replay: no live fetching, no writes, no user-supplied sources.

See [docs/COST_CONTROLS.md](docs/COST_CONTROLS.md) for the numbers and the AWS budget configuration.

## Security posture

Retrieved content is treated as data at every layer: delimited and labelled untrusted in the prompt, handled by an agent with no outbound-capable tools, and validated structurally on the way out. Prompt-injection resistance here is an architectural property, not an instruction.

## Development

```bash
pytest                 # unit tests, no AWS calls
ruff check src tests
```

Tests cover relevant, irrelevant, ambiguous, duplicate, stale, and failed-source cases, and run entirely offline.

## Disclosure

Built with the assistance of AI coding tools (Claude Code), as permitted by the hackathon rules. Third-party dependencies retain their own licenses; see [NOTICE](NOTICE).

## License

[MIT](LICENSE)
