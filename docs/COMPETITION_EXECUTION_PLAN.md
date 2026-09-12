# BuiltWatch: competition and product execution plan

Prepared 12 September 2026. This is a handoff plan, not a claim that the backlog
has shipped. Use the current checkout and preserve uncommitted work.

## Strategic decision

Keep one audience: professionals who already operate several agents, automations,
APIs or apps. The repetitive task is not reading a news feed: it is determining
whether a specific outside development affects a specific system, then documenting
the decision. The product should reduce that work without pretending to inspect
live code or decide business risk for the person.

The differentiator to demonstrate is:
external change → exact saved dependency → supported reasoning → optional agent
investigation → human outcome → new assessment when the profile or change changes.

Do not broaden into general compliance, autonomous remediation, unlimited web
crawling or an all-professions platform before the deadline.

## Competition gate

The official deadline is September 14, 2026 at 5 p.m. Pacific. Strands is required;
AgentCore is optional. The entry needs the public repository and allowed license,
architecture/README, accessible demonstration and a public video no longer than
five minutes. Technical execution, design, potential impact, originality and
presentation are all judged. Confirm the final requirements in the
[official rules](https://agentsforhumans.devpost.com/rules).

Do not move infrastructure solely to add a service logo two days before submission.
Verify repository access from a signed-out browser and video availability, rather
than assuming either exists. Changing repository visibility or publishing a video
requires the owner's authorization and a secret/history audit.

## Implemented in this pass

- A shared coverage state distinguishes new, changed, partial, aborted, unknown and
  checked profiles. Inbox emptiness is no longer used as proof of coverage.
- Profile changes during a scan invalidate the older check conservatively.
- The current registry is compared with retrieved sources, so adding a source does
  not silently inherit a prior full-coverage claim.
- Demo review counts follow actual dispositions; closed items are not labeled
  irrelevant merely to increase a noise-filtering number.
- Refresh restarts after returning from Docs, preserves active forms/search, retains
  private data on temporary failure, and discards out-of-order responses.
- Source groups disclose partial coverage. Search distinguishes no matches from no
  open reviews. Import copy now includes one to ten profiles and discloses the
  post-save check request.
- Current architecture documentation replaces obsolete owner-key/S3 claims.
- New offline state and refresh tests, plus local desktop/mobile browser checks.

No model-quality score, production adoption figure or incident-prevention claim was
created by this work. No new paid model calls or AWS infrastructure changes were needed.

## Execution order and handoff contracts

Give each task below as a separate bounded assignment. Luna/Sol are suggested task
owners, not assurances about what a model can or cannot do. Require tests and an
evidence-backed handoff regardless of the model.

| Order | Task | Suggested owner | Gate before moving on |
|---|---|---|---|
| P0-A | Submission reproducibility and public-entry audit | Luna, owner for publication | Fresh checkout and signed-out demo work |
| P0-B | State-machine browser regressions | Sol | Demo and mocked-private workflows pass |
| P0-C | Judging walkthrough and screenshots | Luna, owner for recording | One coherent 4-minute story, no unsupported claims |
| P1-A | Independent semantic evaluation | Sol builds harness; human labels | Frozen labels, all cases reported, reproducible scoring |
| P1-B | Per-pair assessment receipts and fair coverage | Sol | No omitted or failed pair is reported complete |
| P1-C | Idempotent outcomes and import reconciliation | Sol | Duplicate deliveries and conflicts cannot corrupt state |
| P1-D | Event-derived impact metrics | Sol | Counts reconcile; no duplicate/demo inflation or private payload |
| P1-E | First-use and return-use refinement | Luna after API contracts | Users can identify the next action unaided |
| P2-A | Consented pilots and independent reproduction | Owner with technical support | External attestations and negative results retained |
| P2-B | Scaling, privacy and security hardening | Sol, independent reviewer | Isolation, bounds, deletion and recovery tested |

### P0-A — submission reproducibility

Start with AGENTS.md, ARCHITECTURE.md and the current package scripts. Verify that the
license is one permitted by the competition, the README explains Strands' actual
role, and the demo is available without an account. Document which tests are
deterministic, mocked, replayed and live; do not call them all end-to-end AI tests.
Run a clean-checkout setup using documented commands and record actual failures.

Keep the standalone offline demo working, including new status.js. Search the built
artifact for secret values using a local scanner that does not print secrets. Never
publish data/ credentials, private account fixtures or immigration strategy notes.
Confirm no user project is being made public incidentally.

Acceptance: another developer can build the UI and run the offline suite from the
README; the public entry link works signed out; license, video and submission fields
are explicitly checked off, not inferred from existence of a local file.

### P0-B — repeatable browser coverage

Turn the local browser audit into a portable test with development-only Playwright
configuration and a mocked account API. Cover 390×844, 768×1024 and 1440×1000,
keyboard navigation, modal back/close, validation focus and visible footer actions.
Include a private fixture with zero apps, one new import, an edit during a running
scan, a failed fetch, an aborted scan and a completed scan with no reviews.

Test navigation from Docs while work is running; typing during a network response;
session expiry; stale responses; and no model/network work from demo mutations.
Capture failure screenshots outside production assets. Add accessible error text
near its input, not only a toast.

Acceptance: changes to data actually drive rendered state. Do not replace these tests
with assertions that a phrase exists somewhere in app.js.

### P0-C — presentation

Use one professional, three existing systems and a short saved external-change replay.
Show an irrelevant change, a supported review, and a human choice that needs no app
change. Then edit a dependency and show that the old result is not treated as current.
Show the limited-source case briefly as honest coverage, not as the main product demo.

Suggested video: 0:00 problem/person; 0:30 import; 1:00 grounded triage; 2:00 decision;
2:45 repeat-use behavior; 3:20 AWS/Strands architecture; 3:50 measured evidence and
limitations. Use captions and remove private account details. A live AWS trace may
support the architecture; do not portray a saved replay as a live model invocation.

### P1-A — quality benchmark, not a vanity score

Implement a versioned manifest and evaluator under evaluation/ with source snapshots,
profile snapshots, content hashes, expected relevance and a rationale per case.
Start with 30–50 cases spanning security, deprecation, AI services and regulations.
Split by development/source family, not just wording, so paraphrases cannot leak
between tuning and holdout sets. Freeze labels before inspecting model predictions.

Include unsupported applicability, missing version numbers, malicious source text,
expired proposals, same-name unrelated products, withdrawn advisories, new profiles
against old sources, and failures. Separate text-grounding success from semantic
correctness. Have at least two qualified reviewers label ambiguous holdout cases and
record disagreement; a second model is not independent human validation.

Report confusion matrices, review precision, consequential false negatives, abstention
rate, evidence validity, and useful-review yield. Show sample size and uncertainty.
Compare with keyword matching and a manual-review baseline. Store model/prompt versions,
cost, latency and every failed case. Cached/replay results are labeled separately.

Do not add a public accuracy badge until the benchmark is complete. Start offline;
a live batch must use the remaining approved budget and stop at existing limits.

### P1-B — assessment receipts and coverage scheduling

The UI currently infers freshness from profile time, run status and source health.
Replace inference gradually with a persisted receipt per system/profile-hash and
source/content-hash pair: attempted, screened-out, assessed, cache-hit, failed or
aborted; include run ID, quality/model version and completion time. Persist only
completed pairs in the reusable cache.

A run's systems_evaluated list is assigned before evaluation starts, so it is not
itself proof every pair finished. Test that a budget abort on pair 4 of 10 cannot
make all ten green. Source retrieval is not the same as pair assessment.

When registry or workspace size exceeds per-run ceilings, rotate pending pairs fairly
with a persisted cursor or bounded priority queue. Preserve safety-critical priority
without starving other sources. Do not increase ceilings to mask omitted work.
Migrate existing records as legacy/unknown, never as fabricated successful receipts.

### P1-C — outcomes and imports

Preserve user choices: no change needed, app updated without a new profile, does not
apply with a reason, or keep open. Store user-reported remediation separately from
verified profile freshness. If a profile is stale, show an optional refresh action.

Use stable system IDs; show new/matched/unchanged/conflicting counts before save.
Names are hints, not sufficient evidence for destructive merging. Present ambiguous
matches for explicit confirmation. Preserve fields omitted in a partial update only
under an explicit patch contract; a full replacement must display what will be removed.

Add idempotency keys, tenant-scoped conditional writes and profile-version checks.
Exercise repeated submits, identical replay, renamed app, ID collisions, same name
different apps, stale agent returns, cross-tenant IDs and mid-batch failure.

### P1-D — defensible impact metrics

Avoid scanning every private payload on each public cache miss. Record immutable,
tenant-scoped events with globally unique event IDs and origin: live, test or demo.
Update aggregate counters transactionally/idempotently; reconcile periodically against
source records. Keep personal data out of analytics events.

Define each metric: active saved profiles is a gauge; evaluated pairs counts completed
screen/assessment work; review events count unique material revisions; decisions are
human outcomes, not fixes; agent recommendations are not human decisions. Distinguish
attempts, cached reuse, completed evaluations, abstentions and failures.

Do not turn anonymous demo clicks or developer test accounts into live impact.
For repeat usage, aggregate consented cohorts without exposing small identifiable
groups. Make last-aggregation time and methodology visible. Time saved is optional,
user-reported unless independently observed; do not derive it from arbitrary minutes
per finding. Accept a lower honest number after reconciliation.

### P1-E — usability after the data contracts are stable

Keep the overview focused on one next action: import, check, review or refresh stale
profiles. Expose detailed coverage on demand. Avoid a second competing multi-import
flow. Show successful saves with matched/new counts and a clear check state.

Show notification preferences and paused status consistently. A return visit should
explain what changed since the last visit, not just show a cumulative total. Use
semantic buttons, visible focus, screen-reader status messages and reduced motion.
Do not rebuild the visual system or add a dashboard full of scorecards.

### P2-A — external evidence

Recruit a small genuine pilot, initially 3–5 operators with permission. Measure time
to first useful review, recommendation usefulness, false alarms, missed material
changes, repeat use at 7/30 days and outcomes. Retain denominators and failed cases.
Ask participants to attest to what they actually used and observed; do not draft
preapproved praise. Seek a relevant US pilot or evaluator to test the proposed US
application rather than merely asserting a nationwide benefit.

### P2-B — production hardening

Threat-model tenant isolation, agent token scope, source prompt injection, SSRF,
credential exposure, feedback abuse, race conditions and duplicate worker delivery.
Test account deletion, retention/expiry, budget fail-closed behavior, admission locks,
backups and restoration. Consider a queue/AgentCore migration only after measuring
the operational need and defining rollback. Extract duplicate app.js overrides into
tested modules incrementally, not as a last-minute rewrite.

## Deployment contract for every assignment

1. Inspect the working tree and record the scope; do not overwrite unrelated work.
2. Add behavioral regression tests before changing a state or storage contract.
3. Run syntax, Node, Python and lint gates. Record baseline failures explicitly;
   do not delete a failing correctness test to get green.
4. Build and inspect the actual output, including offline-demo.html.
5. Frontend: use the existing Sites project, push exact source, save and deploy the
   matching build. Preserve audience, domains, environment secrets and bindings.
6. Backend: use infra/deploy_accounts.py only after checking the live account and
   deployment configuration. Back up tables/configuration and use additive migrations.
   Never run the legacy owner-only deploy script as a substitute.
7. Check terminal deployment status. Exercise public/demo plus a disposable private
   test profile, using no model calls unless the task specifically requires a capped
   live check. Delete only the test profile created for that run.
8. Roll back the prior frontend version on a broken path. For backend changes retain
   the previous code/config and use the documented data-compatible rollback. A reverted
   UI does not undo a database migration.
9. Return what changed, test results, production link, limitations and next task.

## Release notes for the next assignee

This pass introduced web/status.js, tests/status.test.mjs and tests/refresh.test.mjs.
Some older Python asset tests only inspect strings; relevant state/refresh assertions
were replaced by behavioral Node coverage. A pre-existing test import was corrected.
The repository also has 12 pre-existing Python lint findings (import ordering, line
length, a suppress suggestion and a punctuation warning); handle them as a separate
format-only cleanup, then rerun the full suite. Do not infer a backend deployment from
this frontend release.
