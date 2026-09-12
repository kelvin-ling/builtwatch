# BuiltWatch — web-first implementation

Professional Agents track. The primary interaction is the responsive web workspace:
remember systems, inspect relevant external developments, and export focused handoffs.
Public sample browsing is read-only; private owner access enables profile management,
live checks, and dispositions. Use Strands/Nova for relevance investigation and a small
serverless deployment with durable history. See README.md for the current product.

## Original brief

# BuiltWatch — project brief

You keep building. BuiltWatch remembers what you built and tells you when the world changes in a way that matters.

## Track and audience

Track: Professional Agents.

Professionals increasingly use AI agents to create applications and automations faster than they can keep track of them. BuiltWatch maintains a lightweight inventory of what has been created and continuously watches for external changes that may require attention, surfacing only the systems that may actually be affected.

The initial audience is independent professionals, makers, and small teams responsible for multiple applications, agents, and automated workflows. BuiltWatch takes on the recurring work of remembering these systems, checking relevant developments, and determining what deserves review. Most of the time it stays quiet.

Core journey: Something gets built → BuiltWatch remembers it → the world changes → BuiltWatch identifies which systems may need attention → a person or builder agent receives a concise finding.

## Product boundary

Remember systems, watch selected external sources, assess relevance, and hand off evidence-backed review requests. No automatic code remediation or legal determinations. No mandatory repository provider or coding agent. Source coverage is explicit, never described as watching the entire world.

Inventory can come from a user, another agent, or a supported import mechanism. Collect only enough information to describe purpose, technologies and services, consequential actions and data flows, and important assumptions or constraints. Source monitoring spans vendor policies, API changes and deprecations, laws and regulations, privacy and AI requirements, communications restrictions, security incidents, failure patterns, and standards or guidance. The initial release implements a small, explicit selection across these categories.

## First complete workflow

1. Describe a system in plain text or import a versioned JSON system passport.
2. Confirm extracted purpose, dependencies, actions, data categories, assumptions, and optional jurisdiction. Preserve unknowns and provenance.
3. Check a small curated source registry on a schedule. Store source snapshots, content hashes, publication/effective/retrieval dates, and fetch health.
4. Use Strands tool calls to retrieve system profiles and source evidence, assess candidate relevance, and emit validated structured findings.
5. Require a source passage and explicit system fact for each relevance claim. Separate facts, inferences, unknowns, and review suggestions. Distinguish proposals from adopted requirements.
6. Deduplicate findings by system, development, and material revision. Suppress irrelevant items; expose coverage failures separately from no relevant changes.
7. Let a person acknowledge, dismiss with a reason, or export a Markdown/JSON builder handoff. Record disposition and prevent repeated unchanged alerts.

## Demonstration

Three systems and a small set of sources spanning vendor/API changes, policy/regulatory developments, and security/failure developments. Show one affected system, one explicitly unaffected system, one insufficient-information case, and a repeat run with no duplicate notification. Use real cited historical material in a clearly labeled replay; keep live retrieval separately identifiable. Show a complete saved handoff, not merely generated chat text.

## Architecture direction

Strands with Bedrock for bounded relevance investigation and structured findings. Persistent system passports, source versions, scan runs, findings, and dispositions. A scheduler invokes the watch pipeline independently of the browser. Target AgentCore if deployment permissions and timing permit. Provide a local runnable mode and neutral HTTP/JSON import/export. Choose final hosting and database after AWS capability checks. Public demonstration uses sample inventory; private inventory requires access control.

## Implementation and attribution

Write a fresh implementation designed specifically for BuiltWatch. Do not copy code, prompts, datasets, assets, or documentation from the user's existing projects, or make them product dependencies. Choose architecture and abstractions for this workflow rather than preserving earlier project designs. No existing-project code has been copied.

No attribution to earlier projects is needed for code that is not incorporated. Retain the required licenses and notices for Strands and other third-party dependencies, cite external evidence, and accurately disclose any pre-existing work actually incorporated under the hackathon rules. Do not claim a clean-room process: earlier project material was inspected during planning.

## Access audit

Re-run 8 September 2026. Supersedes the earlier provisional audit.

**Verified working:**

- Local workspace writable; repository `kelvin-ling/builtwatch` cloned over SSH as
  `kelvin-ling`. Repo is currently **private** and must be made public before submission.
- Python 3.12.14 installed via `uv` at `~/.local/bin/python3.12`. System Python 3.9.6
  cannot run this project (Strands requires >= 3.10).
- `strands-agents 1.54.0` and `strands-agents-tools 0.8.8` install and import cleanly.
- AWS IAM user `kling` on account `561217459367` holds **AdministratorAccess** via the
  `admin` group. The earlier "AWS CLI does not recognise Bedrock" observation was a CLI
  version artifact (2.11.24), not an IAM problem — current boto3 resolves it.
- Bedrock **control plane** works: `ListFoundationModels` returns 122 models;
  `ListInferenceProfiles` returns the Claude profiles.
- **AgentCore control plane reachable**: `bedrock-agentcore-control:ListAgentRuntimes`
  succeeds. Deployment target is viable.
- DynamoDB, S3, Lambda, EventBridge Scheduler, ECR, CodeBuild, App Runner, CloudWatch Logs
  all callable.
- All 11 registry sources fetch successfully over the production fetch path.
- AWS Budget `builtwatch-monthly-20usd` created: $20/month, alerts at 50/80/100% actual and
  100% forecasted to the owner-configured alert address.

**Blocked:**

- **Bedrock model invocation is denied at the account level.** Every model, including
  Amazon Nova, returns `ValidationException: Error 002: Access to Bedrock models is not
  allowed for this account`. Root cause established:
  `get_use_case_for_model_access` returns *"You have not filled out the request form"*,
  and Anthropic models report `agreementAvailability = NOT_AVAILABLE` while
  `entitlementAvailability = AVAILABLE` and `authorizationStatus = AUTHORIZED`.
  The account has never submitted the Bedrock model-access use-case form. Remediation is a
  console action by the account owner — it is an acceptance of model provider terms and is
  not something an agent should perform on the owner's behalf. Steps are in
  `docs/SUBMISSION_CHECKLIST.md`.
- SSO profile `[aws-profile-redacted]` (account `[aws-account-redacted]`, AdministratorAccess) has an
  expired token. Available as a fallback account if the primary cannot be unblocked, but it
  would need `aws sso login` and its own Bedrock enablement.

**Cost posture:** $20/month ceiling approved by the owner. In-app ceilings default to $0.25
per run, $1.00 per day, $15.00 per month, enforced by a Strands hook that aborts rather than
degrades. Spend is ledgered in SQLite and read back across restarts. No paid model
invocation has succeeded yet, so **spend to date is $0.00**.

## Acceptance criteria

- Text and JSON intake both persist usable system profiles.
- Source fetch failures cannot look like successful quiet scans.
- Findings cite fetched evidence and matching profile facts.
- Unsupported conclusions and missing applicability facts remain explicit.
- Repeated unchanged scans do not duplicate findings.
- Stored content cannot issue instructions or trigger arbitrary outbound actions.
- A finding can be exported, acknowledged, and revisited after restart.
- Strands executes the relevance workflow in the real-model path.
- Tests cover relevant, irrelevant, ambiguous, duplicate, stale, and failed-source cases.
- README, architecture diagram, dependency notices and any required disclosures, license, demo, and submission copy reflect actual behavior.

## Current stage

Implementation underway as of 8 September 2026. Named **BuiltWatch**; `builtwatch.org`,
`.com`, `.io`, `.dev`, `.app` and `.net` were all confirmed unregistered — none yet
purchased.

**Built and verified offline:**

- Domain models with grounding validation as a type-level property.
- SQLite store with dedup, supersession, dispositions and a cost ledger.
- Curated 11-source registry across all seven categories, plus a captured replay corpus of
  real retrieved material.
- Hardened fetcher: HTTPS-only, public-IP-only (SSRF defence), no cross-host redirects,
  streaming size cap.
- Two-stage Strands pipeline: Haiku screen, Sonnet tool-using assessment with four
  read-only tools, `BudgetGuard` hooks enforcing spend and iteration ceilings.
- Grounding conversion that rejects fabricated quotes and non-existent passport facts, and
  downgrades ungrounded "relevant" claims rather than publishing them.
- Intake from plain text and neutral JSON; Markdown and JSON builder handoff export.
- Full CLI covering every product function.
- 41 tests, all passing offline with no AWS calls, covering relevant, irrelevant,
  ambiguous, duplicate, stale, failed-source and budget-abort cases. `ruff` clean.

**Not yet done:**

- The real-model path has never executed successfully — blocked on Bedrock account access.
- AgentCore Runtime deployment and the EventBridge schedule.
- Demo video, submission copy, and flipping the repository to public.
