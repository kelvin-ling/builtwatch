> **Public pilot:** Independent email registration, private workspaces, an interactive no-account demo, agent-prepared profiles, and revocable daily builder-agent connections. See [the user guide](docs/ACCOUNTS.md) and [pilot architecture and limits](docs/PUBLIC_LAUNCH.md).

# BuiltWatch

**BuiltWatch watches external changes that could affect the AI agents, automations, APIs, and apps you already run, then tells you what deserves attention and why.**

Built for the [Agents for Humans hackathon](https://agentsforhumans.devpost.com/) — *Professional Agents* track. Powered by [Strands Agents](https://github.com/strands-agents/sdk-python) on Amazon Bedrock.

---

## The problem

AI coding tools made it cheap to build things. They did not make it cheap to *remember* them.

Developers, technical makers, consultants, and small teams now run several small systems: agents, API integrations, automations, and web apps. Each one quietly depends on service policies, API versions, software dependencies, security assumptions, and regulations that can change after launch.

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
- **It records uncertainty.** When an applicability fact is missing from a system's profile, it returns `insufficient_information` and names the missing fact.

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

Extraction is instructed to preserve gaps rather than invent details; users should review the profile. Anything it could not determine lands in `unknowns` and stays visible.

### 2. A curated source registry

`sources/registry.yaml` is the only place a fetchable URL can come from. Nothing a user types, and nothing a fetched document says, can add a URL to it. Coverage spans vendor policies, API changes and deprecations, laws and regulations, privacy and AI requirements, communications restrictions, security incidents, and standards guidance.

### 3. A two-stage relevance investigation

This is where Strands does the work, and it is split in two for a reason — cost.

**Stage 1 — screen** (Amazon Nova Lite, no tools, high recall). For each (system, change) pair: could this plausibly matter? Most pairs die here for a fraction of a cent.

**Stage 2 — assess** (Amazon Nova Pro, tool-using, bounded). Survivors get a real investigation. The agent must call tools to read the passport and the evidence before it can answer:

| Tool | What it does |
|---|---|
| `get_system_passport` | The profile, plus the exact `fact_index` keys it is allowed to cite |
| `list_evidence` | Which source documents are readable this run |
| `read_evidence` | A chunk of one document, wrapped in `<evidence>` delimiters |
| `search_evidence` | Targeted passage lookup inside long documents |

Every tool is read-only. **There is no tool that fetches a URL, sends a message, writes a passport, or runs code.** Retrieved text can still influence the model’s reasoning. Read-only tools limit its ability to act.

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

## Web workspace

Open **https://builtwatch.org**.

The public sample workspace shows saved, real Strands/Nova replay results for three
example systems. It is read-only and never invokes a model. Findings are historical
assessments, not announcements of newly detected changes today.

Choose **Open your workspace** and enter the private access key supplied with the
deployment. The key stays in browser session storage. The owner workspace supports:

- Add and edit system profiles with a plain-language form, or import neutral JSON.
- Review findings, source passages, applicability facts, unknowns, and suggested actions.
- Acknowledge or dismiss findings; download a Markdown builder handoff or JSON profile.
- Inspect source coverage and check history, including incomplete checks and model cost.
- Request a live check; automatic checks run daily at 7 a.m. America/Toronto.

No repository provider is required. Profile entry is manual and free of model charges;
the CLI additionally supports model-assisted plain-text extraction.

This deployment is a **single-owner workspace**, protected by a high-entropy access key.
It does not offer public account registration or multiple independent tenants.
A running check may temporarily make the private API busy; the static sample remains
available. Keep the access key private. Local access instructions are in the gitignored
`data/WORKSPACE_ACCESS.md` file created at deployment.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full diagram and the deployed AWS
topology. Continuing this work? Start at [docs/HANDOFF.md](docs/HANDOFF.md).

## Quick start

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
source .venv/bin/activate

builtwatch source list                      # exactly what is watched
builtwatch system import examples/passports/inbox-triage.json
builtwatch scan --mode replay               # reproducible historical retrieval; model calls are metered
builtwatch finding list
```

`--mode replay` runs against committed, dated snapshots in `replay/` — real material captured from the registry sources, clearly labelled as a replay. `--mode live` performs real HTTPS retrieval. The two are never mixed or confused: every snapshot records which it was.

## Cost and abuse resistance

BuiltWatch minimizes idle compute and avoids anonymous AI spending.

- The frontend is static. Lambda has no provisioned concurrency or always-on server.
- Estimated model usage is checked before calls: $0.25/run, $0.50/day, $10/month
  in the web deployment. An in-flight call can exceed a threshold before usage is known.
- Acknowledged findings can surface again when their material evidence changes.
- Completed assessments are cached by profile, source content, and live/replay mode.
  New profiles, edited profiles, and interrupted pairs are still assessed.
- Retrieval is bounded and limited to the committed source registry.
- API reads and writes require the owner's key; public visitors use static sample data.
- Private SQLite checkpoints are encrypted in S3, with one concurrent Lambda writer.
  Storage, requests, bandwidth, and logs can still incur charges; no zero-cost guarantee.

See [docs/COST_CONTROLS.md](docs/COST_CONTROLS.md) for the numbers and the AWS budget configuration.

## Security posture

Retrieved content is treated as data at every layer: delimited and labelled untrusted in the prompt, handled by an agent with no outbound-capable tools, and validated structurally on the way out. These controls reduce prompt-injection risk; they do not prove the model’s conclusions are correct.

## Development

```bash
pytest                 # unit tests, no AWS calls
ruff check src tests
```

Tests cover relevant, irrelevant, ambiguous, duplicate, stale, and failed-source cases, and run entirely offline.

## Disclosure

Built with the assistance of AI coding tools (Claude Code and OpenAI Codex), as permitted by the hackathon rules. Third-party dependencies retain their own licenses; see [NOTICE](NOTICE).

## License

[MIT](LICENSE)

## Current public pilot (September 2026)

The account-based deployment supersedes the earlier single-owner deployment limits above.
See [current cost controls](docs/COST_CONTROLS.md) for the CAD 25 monthly target, USD 5
shared model reserve, daily billing guard and owner dashboard.

**Import apps** copies a request for the agent that knows your projects. Paste its JSON
or upload the file, review up to ten app profiles together, then confirm the import.
Importing costs no model credits. Only the projects accessible to that agent can be
included; BuiltWatch does not secretly discover or access other conversations.

Evidence is selected from exact source passages. Unverifiable assessments are withheld
as check-quality notices, not requests for more user information. Named vendor and
product checks prevent generic monitoring purposes from implying unrelated dependencies.
This reduces false positives; model judgments still require human review.

The signed-in owner can open **Owner dashboard** to see cached costs, registrations,
workspaces, request usage and warnings, and pause paid checks. Other accounts and agent
connection tokens cannot access this dashboard. SNS email warnings require the recipient
to confirm the AWS subscription email.

### System context

BuiltWatch records software dependencies alongside operating conditions and human
checks. The current experience is intentionally focused on developers and technical
operators running agents, automations, API integrations and small applications.

Describe the work your automation does and what must stay true: for example, a quote
helper assumes its price list is current and a person approves the quote. Intake and
agent exports preserve that context. The optional Business context editor uses the
same saved profile, without a separate questionnaire or new mandatory fields.

The screening agent now sees recorded actions, assumptions and constraints. Its review
must connect a source development to a specific recorded fact; it may not invent
commercial impact. Live coverage is 12 curated sources, now including the US FTC
Business Blog summaries. This is bounded source monitoring, not an all-news service.
The existing monthly spending controls remain unchanged.

### App-specific review briefs

Review items lead with the affected app and show the cited app detail, source development,
possible consequence and concrete review question. Results are grouped by app. Older
findings use their existing recorded facts and reasoning, without paid rewriting. If
those facts no longer match the app profile, the brief flags that the connection needs
rechecking. New relevant assessments must include an app-impact explanation anchored to
a cited fact; unsupported explanations are withheld. Consequences remain reasoning to
verify, not guarantees of impact.

The current hosting is AWS application services plus a Sites/Cloudflare website and
gateway. A custom domain can attach to the same Site; see [cutover steps](docs/CUSTOM_DOMAIN.md).
