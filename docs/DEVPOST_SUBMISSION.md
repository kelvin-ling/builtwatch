# Devpost submission text

Copy each section into the matching Devpost field. Every figure below is measured from the
repository or a recorded run; none is an estimate.

**Track:** Professional Agents
**Live demo:** https://builtwatch.org
**Code:** https://github.com/kelvin-ling/builtwatch
**Video:** *(add the public YouTube or Vimeo link)*

---

## Tagline

Impact monitoring for the systems you already run: BuiltWatch remembers what you built,
watches what changed, and tells you only what affects you, with evidence.

## Inspiration

AI coding tools made it cheap to build agents, automations and integrations. They did not
make it cheap to remember them. After a few months, an independent builder is running a
dozen small systems, each depending on vendor policies, API versions, security advisories
and regulations they do not control. Those change constantly, and changelogs cannot say
whether a change matters, because they have never seen what you built. Most people find
out when something breaks.

## What it does

- **Remembers what you built.** A short profile of each system, imported from the coding
  agent that built it or written by hand. No source code or credentials. Unknown details
  stay marked unknown instead of being guessed.
- **Watches a curated, explicit set of sources.** 21 official sources across 8 categories:
  API and platform changes, security advisories, AI service policies, regulation, privacy
  guidance, sender requirements, engineering standards and enforcement news.
- **Judges relevance per system.** For every system and source, an agent asks whether this
  specific change affects this specific system. Most do not, and BuiltWatch stays quiet.
- **Shows its evidence.** Each finding quotes the source passage word for word, names the
  profile fact that makes it relevant, and separates facts, inferences and unknowns.
- **Keeps a person in control.** Record "no app change needed", "the app was updated" or
  "this does not apply", or export a prepared review to a coding agent. Nothing changes
  automatically.
- **Makes coverage explicit.** A source that could not be fetched is shown as a coverage
  gap, never as an all-clear. A repeat check with nothing new stays silent.

## How we built it

**Strands Agents** drives every model-backed step:

- An **intake agent** turns a plain-text description into a structured system profile,
  preserving what it could not determine.
- A **screening agent** on **Amazon Nova Lite** discards clearly unrelated
  system–source pairs cheaply.
- An **assessment agent** on **Amazon Nova Pro** investigates the rest with four
  read-only tools (profile, evidence list, read evidence, search evidence) and returns a
  structured finding.
- **Strands hooks** meter tokens on every model call and abort a run at its per-run and
  per-day ceilings.

Every finding then passes deterministic validation: quoted passages must exist verbatim in
the stored snapshot, cited facts must exist in the profile, and any claim that the system
uses something its profile never declares is rejected.

**On AWS:** an API Lambda and a background worker Lambda, DynamoDB for tenant-partitioned
workspaces and conditional spend reservations, Amazon Cognito for email sign-in, EventBridge
Scheduler for the daily check, and a cost monitor Lambda that reads Cost Explorer, alerts
the owner through SNS, and pauses paid checks when spend or billing data looks unsafe. The
web UI and signed gateway run on Cloudflare (Sites, Worker, D1).

## Challenges we ran into

- **A budget guard that silently did nothing.** Scans reported $0.00 while spending real
  money: the deprecated structured-output call path fires no Strands model hooks. All call
  sites were moved to `structured_output_model`, with usage read as live deltas.
- **A confident, fabricated finding.** The model flagged a Microsoft Windows vulnerability
  as relevant to a system with no Windows anywhere in its profile. Structurally the finding
  looked valid. It is now rejected by an evidence-driven rule that needs no product
  allowlist.
- **Fixed rules that kept serving old verdicts.** Findings are stamped with a quality
  version, so a corrected rule withdraws the verdicts it would no longer make.
- **Honest coverage.** Distinguishing "nothing relevant changed" from "we could not check"
  took explicit per-source health on every run.

## Accomplishments that we're proud of

- A complete real run of 3 systems against 21 sources (63 pairs) on Amazon Bedrock cost
  **$0.18**. 27 pairs were screened out by Nova Lite, 36 were assessed by Nova Pro, and
  no source failed.
- **195 automated tests** (147 Python, 48 JavaScript) cover relevant, irrelevant,
  ambiguous, duplicate, stale and failed-source cases.
- Zero outbound actions: the watch is read-only, and spend ceilings fail closed.

## What we learned

An agent is only useful for professional work when it can show why it reached a conclusion
and admit when it cannot. Validation, coverage reporting and spend limits turned out to be
the product, not overhead.

## What's next for BuiltWatch

- Per-pair assessment receipts, so coverage can be proven system by system.
- User-selected sources beyond the curated registry.
- Stronger models through the existing model ladder as entitlements allow.
- Evaluating Amazon Bedrock AgentCore for the background worker.

## Built with

strands-agents · amazon-bedrock · amazon-nova · aws-lambda · amazon-dynamodb ·
amazon-cognito · amazon-eventbridge · aws-cost-explorer · amazon-sns · python · pydantic ·
javascript · cloudflare-workers

## AI assistance disclosure

Developed with AI coding assistance (Claude Code and OpenAI Codex), as permitted by the
rules and disclosed in `NOTICE`.
