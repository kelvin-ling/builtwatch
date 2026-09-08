# Precision: measured, and honestly reported

A watcher that cries wolf is worse than no watcher. This is what BuiltWatch actually
produces against real models, and where it still falls short.

## Setup

Three systems, deliberately chosen to cover the three answers the product can give:

| System | External services | Recorded unknowns | Expected |
|---|---|---|---|
| `inbox-triage` | Gmail API, Bedrock, SendGrid | none | affected |
| `recipe-site` | none — static Hugo site | none | unaffected |
| `support-widget` | Bedrock | 3, incl. jurisdiction | undecidable |

Eleven sources, all changed (first run, so everything is new). Models: Amazon Nova Lite
screening, Nova Pro assessing. Anthropic models were unavailable on this account.

## Result

| | Run 1 | Run 2 (materiality bar + stated-fact requirement) |
|---|---|---|
| `relevant` total | 7 | **3** |
| `inbox-triage` relevant | 4 | 3 |
| `support-widget` relevant | 3 | **0** |
| `recipe-site` relevant | **0** | **0** |
| findings with a stated source fact | 0 | all |
| downgraded by the validator | 5 | 4 |
| cost | $0.2539 | $0.2542 |

Noise dropped by 57% at identical cost.

**`recipe-site` never produced a false positive in either run.** A static site with no
external services was correctly told "nothing here concerns you" 9 times out of 9, then
6 out of 6. This is the hardest thing for a watcher to do and the easiest to get wrong.

**`support-widget` moved from 3 false alarms to 4 honest `insufficient_information`
answers.** That system has jurisdiction unrecorded, so the EU AI Act question genuinely
cannot be answered from its passport. Saying so is the correct behaviour.

## What the validator caught

Across both runs the grounding validator downgraded 9 claims that the model asserted as
`relevant`:

- **2 fabricated quotes** — passages that did not appear in the stored snapshot at all;
- **7 claims with no evidence passage** — a verdict asserted with nothing behind it.

None of these reached the user as findings. They appear as `insufficient_information`
with the reason attached. This is the single most important property in the system, and
it was exercised by a real model genuinely trying to over-claim — not by a synthetic test.

## Where it still falls short

Being straight about this rather than showing only the good runs:

1. **Standing policy still slips through.** "Anthropic Usage Policy relevance to
   inbox-triage" survives as `relevant`, but the AUP has always applied and nothing about
   it changed. The materiality bar catches "new model released"; it does not yet
   reliably catch "this rule already applied to you yesterday". The fix is diffing against
   the previous snapshot rather than assessing the current one whole — worth doing, not
   done.
2. **Nova Pro fabricates.** Two invented quotes in 57 assessments. The validator caught
   both, but a model that triggers the validator repeatedly wastes money reaching a
   downgraded answer. Anthropic models would likely reduce this; that account has not been
   entitled, so it is untested here.
3. **Review suggestions are generic.** "Review the policy to ensure compliance" is not
   worth a person's attention. Better suggestions need the passport to carry more
   implementation detail than three example systems provide.

## Reproducing

```bash
builtwatch system import examples/passports/inbox-triage.json
builtwatch system import examples/passports/recipe-site.json
builtwatch system import examples/passports/support-widget.json
builtwatch scan --mode replay
builtwatch scan --mode replay   # second run: 0 findings, $0.0000
```
