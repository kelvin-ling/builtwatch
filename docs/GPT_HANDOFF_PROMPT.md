# Handoff prompt for the ChatGPT/Codex agent

> **Completed 10 September 2026:** the pending frontend work described below shipped in
> Sites version 21. The live assets now include categorized watched sources, group-level
> coverage failures, the modal scroll/footer correction, and the refreshed `?v=20` cache
> key. Do not repeat this deployment. The broader source expansion remains intentionally
> deferred because it would increase recurring assessment cost and should be chosen as a
> separate product decision. The live registry currently has 19 sources across 8
> categories; do not repeat the old “12 sources” count below.

Paste everything below the line into a fresh ChatGPT session once usage resets.

---

You previously built the BuiltWatch web workspace (repo: `kelvin-ling/builtwatch`, local
path `<local-user>/Downloads/Agents-for-Humans/builtwatch`). You ran out of usage mid-task.
Since then a Claude Code session made backend fixes and one frontend change. Everything is
committed and pushed to `main`; pull before you start.

**Read `docs/ISSUES.md` first — it is the authoritative issue register.** Then
`docs/DEPLOY.md` (AWS runbook) and `docs/HANDOFF.md` (environment setup).

## First job completed: frontend deployed

BW-12 is closed. Sites version 21 serves the categorized Watched Sources view and the
modal scroll/footer correction under the refreshed `?v=20` asset key. Live HTTP checks
confirmed `CATEGORY_ORDER`, `source-group`, and `modal-footer` are present.

**A backend deploy and full re-scan already happened on 10 Sep and must NOT be repeated as
a matter of routine.** It was held back until the fixes were complete, then run once. The
frontend deploy needs no re-scan — it is static assets only. Only re-run
`infra/deploy_accounts.py` and the `{"task":"daily"}` invocation if you change Python under
`src/builtwatch/` or `infra/`, and follow `docs/DEPLOY.md` step 4 if you do.

## What changed since you stopped

Seven commits, `e65ddde..7cd4feb`. Test count went 102 → 124; `ruff check src tests infra`
is clean; nothing you wrote was reverted.

| ID | Change | State |
|---|---|---|
| BW-1 | Rejects fabricated dependencies in findings | ✅ deployed |
| BW-2 | `QUALITY_VERSION` retracts findings a fixed rule would no longer make | ✅ deployed |
| BW-4 | Submission checklist corrected against live state | ✅ docs |
| BW-7 | `admit()` no longer masks its return value | ✅ deployed |
| BW-8 | `infra/` lint clean (33 → 0) | ✅ deployed |
| BW-11 | `is_disposed()` settled as a decision | ✅ docs + test |
| — | **Watched sources grouped by category** | ✅ deployed |

Details that affect how you work on this:

- **BW-1** replaced a seven-product allowlist bound to a hardcoded `cisa-kev` source id with
  two allowlist-free rules in `src/builtwatch/quality.py`:
  `affected_product_undeclared()` (a security advisory naming nothing the passport declares
  cannot be relevant) and `unsupported_usage_claims()` (any assertion the system *uses*
  something absent from its passport is ungrounded). Matching is **whole-token, never
  substring** — substring matching made `"act"` from "EU AI Act" match `"actively
  exploited"`. Do not reintroduce substring matching.
- **BW-2** added `QUALITY_VERSION` (currently `4`) in `quality.py`. It is mixed into the
  assessment cache key *and* stamped on each finding; both stores refuse to serve findings
  from an older generation. **If you change an assessment rule, bump it** — otherwise the
  cache skips re-assessment and stale verdicts keep being served.
- **The frontend change** rewrote `sourcesView()` in `web/app.js` to group by category, with
  a heading, blurb, count and per-group status for each. A failed fetch now shows an amber
  "N could not be checked" on the group header, not just the per-row pill. Styles were
  appended to `web/style.css` (`.source-group`, `.source-group-head`,
  `.source-group-status`, `.source-count`).

Post-deploy verification of the backend work, for context: `CVE-2026-85880` ("The system
uses Microsoft Windows" against a passport listing only Strands, the AWS SDK and Cloudflare
Workers) is absent from both tenants, no relevant finding carries an undeclared dependency,
and `insufficient_information` fell from 27% to 13%.

## Your second job: expand the watched sources (only after an explicit cost decision)

The owner wants broader coverage. There are currently **19 sources across 8 categories**,
with 9 under `api_change`, 3 under `security`, 2 under `privacy_ai`, and one or two in
the remaining categories. The prior 12-source count is historical.

Target roughly **20–25 sources**, weighted toward what independent builders running apps,
agents and automations actually get caught by. Gaps worth filling:

- **security** — badly under-covered with one source. GitHub Advisory Database, OSV.dev,
  or an NVD feed.
- **api_change** — Cloudflare Workers changelog (BuiltWatch itself runs on Workers), OpenAI
  deprecations, Google/Azure AI service deprecations, `endoflife.date` for runtime EOL.
- **communications** — Microsoft/Outlook and Yahoo bulk sender requirements, to sit
  alongside Gmail.
- **regulation** — EU Digital Services Act, the European Accessibility Act, US state
  privacy law trackers, Colorado AI Act.
- **vendor_policy** — app store review policies (Apple, Google Play) for anyone shipping
  mobile.

Each source must satisfy the existing contract:

- HTTPS only. `Source.url` rejects anything else, and the fetcher refuses cross-host
  redirects and non-public IPs. **Test every candidate URL with a real fetch first** — a
  `301` in `source_health` means the registry URL is wrong, not the fetcher.
- Fetchable without JavaScript, with reasonably stable dated entries.
- Authoritative publisher, and `notes` must be honest about it. Follow the existing EU AI
  Act entry, which states plainly that it is an unofficial consolidated text and findings
  should be verified against EUR-Lex.
- **If you introduce a new category**, add it in three places or the suite fails:
  `topics` in `web/perspectives.js`, `BLURBS` and `CATEGORY_ORDER` in `web/app.js`. The test
  `test_every_registry_category_has_a_display_name_and_blurb` enforces this — it exists
  because a missing label silently renders a blank group heading.
- Refresh the replay corpus with `python scripts/capture_replay.py` so the demo stays
  consistent, and keep `web/demo.json` in step.

## Cost discipline — read before adding sources

The owner's ceiling is low and this is the change most likely to breach it. **Assessment
cost scales with systems × sources**, so going from 12 to 24 sources doubles the pairs
screened per run.

Current position: `GLOBAL_MONTH_LIMIT` is **$5.00/month** shared, `$0.6392` used as of
10 Sep. A full re-scan of two tenants cost about **$0.10**. The AWS budget is **$12/month**.

- Keep screening on `nova-lite` and assessment on `nova-pro`. Do not raise the models.
- Do not raise `BW_MAX_RUN_USD` (0.25), `BW_MAX_DAY_USD` (0.50) or `BW_MAX_MONTH_USD`
  (2.00) on the deployed Lambdas to make something fit. If a run trips a ceiling, that is
  the ceiling working.
- The cheap screening stage exists precisely so more sources stay affordable — most pairs
  should be screened out before the expensive assessment. If they are not, the screening
  prompt needs work, not a bigger budget.
- Test with `BW_MAX_SOURCES=2` and a single system while iterating.
- After adding sources, run **one** re-scan and report the actual delta in the shared
  reserve before adding more.

## Also outstanding

- **BW-9** — an orphaned single-tenant stack (`builtwatch-workspace` Lambda, its S3 bucket,
  a disabled schedule) from the superseded design. Its function URL is still live. Confirm
  the data is migrated, then ask the owner before deleting anything.
- **BW-10** — 2 of 15 assessments still return `insufficient_information`, both on one
  tenant. Worth reading before further prompt changes.
- **BW-5** — the demo runs on `builtwatch.org`, a ChatGPT-branded
  domain, for an AWS competition. `builtwatch.org`, `.com`, `.io` and `.dev` were all
  unregistered on 8 Sep. Owner decision; `docs/CUSTOM_DOMAIN.md` exists.
- **BW-3** — the repository is still private. Contest rules require it public with an OSI
  licence before **14 September 2026, 17:00 PT**. Owner action only. Remind them.

## Ground rules

- Run `.venv/bin/python -m pytest tests/ -q` and
  `.venv/bin/python -m ruff check src tests infra` before and after every change. The
  test suite is green; the current checkout still has 13 inherited style findings that
  should be handled as a separate format-only cleanup rather than hidden or deleted.
- Do not weaken the seven invariants in `AGENTS.md`. In particular a failed fetch must never
  read as silence, and a relevance claim must stay grounded or be downgraded.
- `NOTICE` discloses AI assistance and the contest requires that to stay accurate — it
  already names both Claude Code and OpenAI Codex.
- Update `docs/ISSUES.md` as you close things, and say plainly what is deployed versus
  merely committed. That distinction is what BW-12 exists to record.
