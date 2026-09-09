# Working on BuiltWatch

Orientation for anyone — human or agent — picking this up mid-flight. Read this before
changing code. Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design reasoning.

## Setup

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
source .venv/bin/activate
pytest                      # 41 tests, fully offline, no AWS calls
```

Python 3.12 lives at `~/.local/bin/python3.12` (installed via `uv`). System Python is
3.9 and **cannot** run this — Strands requires ≥3.10.

## The invariants

These are the product. Changing code that weakens one of them is a regression even if the
tests still pass — so add a test instead.

1. **A failed fetch is never silence.** Any source that could not be retrieved appears in
   `ScanRun.source_health` with a non-OK status and is reported separately from findings.
   *Guarded by:* `test_pipeline.py::test_failed_source_is_a_loud_coverage_failure`
2. **A relevance claim is grounded or it is downgraded.** Every quoted passage must appear
   verbatim in the stored snapshot; every cited fact key must exist in the passport's
   `fact_index` with a matching value. Failure downgrades to `insufficient_information`
   with the reason attached — it never publishes anyway.
   *Guarded by:* `test_grounding.py` (8 tests)
3. **A repeat scan is quiet.** Dedup is `(system_id, development_key)` + a `revision_hash`
   over material substance. Cosmetic churn must not re-notify.
   *Guarded by:* `test_dedup.py`, `test_pipeline.py::test_rewritten_source_does_not_re_notify_the_same_development`
4. **A proposal is not a requirement.** `adoption_status` is carried end to end and
   surfaced prominently in exports.
5. **Nothing retrieved can act.** The agent's tools are read-only. Do not add a tool that
   fetches, sends, writes, or executes. If you need one, it belongs outside the agent loop.
6. **Ceilings abort, they don't degrade.** `BudgetGuard` raises; the run is marked
   `aborted` with a reason.
7. **Coverage is explicit.** `sources/registry.yaml` is the only source of fetchable URLs.
   Never accept a URL from user input, a document, or model output.

## Layout

```
src/builtwatch/
  models.py        domain types + validate_grounding
  config.py        settings, pricing, CostMeter, ceilings
  store.py         SQLite: dedup, dispositions, cost ledger
  registry.py      curated source list
  fetch.py         live + replay retrieval, SSRF defences
  pipeline.py      one watch pass
  intake.py        text extraction + JSON import
  export.py        Markdown / JSON handoff
  cli.py           local runnable mode
  agent/
    prompts.py     both stages' system prompts
    tools.py       four read-only Strands tools
    guard.py       BudgetGuard hooks
    relevance.py   screen + assess + grounding conversion
sources/registry.yaml    what is watched (edit deliberately)
replay/                  captured real snapshots (scripts/capture_replay.py)
examples/passports/      three demo systems
```

## Conventions

- Type hints everywhere; `from __future__ import annotations` at the top of each module.
- Pydantic v2 for anything crossing a boundary (model output, import/export, storage).
- Comments explain **why**, not what. If a line needs a "what" comment, rename something.
- Never widen a ceiling to make something pass. Fix the thing that overran.
- `ruff check src tests` before committing.

## Cost discipline while developing

Real model calls cost money. The owner targets CAD 25/month; shared model reservations are USD 5/month. See docs/COST_CONTROLS.md for the layered safeguards and their limits.

- `pytest` never calls AWS — stub `pipeline.screen` / `pipeline.assess` with `monkeypatch`.
- Use `--mode replay` unless you are specifically testing live retrieval.
- Scope experiments: `BW_MAX_SOURCES=2 builtwatch scan --system inbox-triage`
- `builtwatch status` shows spend against ceilings.

## Picking this up cold?

**Start with [docs/HANDOFF.md](docs/HANDOFF.md).** It carries the AWS access setup, the
model configuration (Anthropic is not entitled on this account — use Nova), exact
reproduction commands, current state, and the traps that have already cost time.

Then [docs/SUBMISSION_CHECKLIST.md](docs/SUBMISSION_CHECKLIST.md) for what is outstanding.
