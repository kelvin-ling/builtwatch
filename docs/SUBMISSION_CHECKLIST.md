# Submission checklist — Agents for Humans

**Submission closes: 14 September 2026, 17:00 PT.**
Judging: 15 September – 8 October 2026. Winners: 14 October 2026.

## Hackathon requirements

| Requirement | Status | Notes |
|---|---|---|
| Built with Strands Agents SDK | ✅ | `strands-agents 1.54.0`; two agent stages, four custom tools, hook-based guards |
| AWS account | ✅ | `561217459367`, IAM user `kling`, AdministratorAccess |
| AWS Builder ID | ✅ | Kelvin Ling / `[owner-email-redacted]` |
| $50 AWS credits requested | ✅ | Submitted before the 11 Sep 12:00 PT cutoff |
| Public code repository | ⛔ **BLOCKER** | Repo is currently **private**. Rules require public with an OSI license. **Must be flipped to public before submission.** |
| MIT or Apache license | ✅ | [MIT](../LICENSE) + [NOTICE](../NOTICE) |
| README | ✅ | [README.md](../README.md) |
| Architecture diagram | ✅ | [ARCHITECTURE.md](ARCHITECTURE.md) — Mermaid, renders on GitHub |
| Demo video ≤ 5 min | ⬜ | Script drafted below; **Kelvin must record and narrate** |
| Text description of features | ⬜ | Draft from README once the demo is final |
| Functioning end-to-end agent | ⚠️ | Complete and tested offline. **Real-model path blocked on Bedrock access** (below). |
| AI assistance disclosed | ✅ | [NOTICE](../NOTICE) and README |
| Newly created in submission period | ✅ | First commit 8 Sep 2026; no prior code incorporated |
| Live demo link *(bonus)* | ⬜ | Optional. `builtwatch.org` available but unregistered. |
| builder.aws blog post *(bonus)* | ⬜ | Up to +0.6 (0.2 × 3 posts) |

## Open blockers

### 1. Bedrock model access is not enabled — **critical path**

Every model invocation fails:

```
ValidationException: Error 002: Access to Bedrock models is not allowed for this account
```

Diagnosed, and it is **not** an IAM problem — the user has AdministratorAccess and the
control plane works fine (`ListFoundationModels` returns 122 models):

```
get_use_case_for_model_access  → ResourceNotFoundException:
    "You have not filled out the request form. Fill out the form before getting access."

anthropic.claude-sonnet-4-5   agreement=NOT_AVAILABLE  entitlement=AVAILABLE  auth=AUTHORIZED
amazon.nova-lite-v1:0         agreement=AVAILABLE      entitlement=AVAILABLE  auth=AUTHORIZED
```

The account has never submitted the Bedrock model-access use-case form, so no model
agreement exists.

**Fix — console, ~3 minutes, must be done by the account owner** (it is an acceptance of
model provider terms):

1. Sign in to the AWS console as account `561217459367`, region **us-east-1**.
2. Go to **Amazon Bedrock → Model access** (left nav, under Configure and learn).
3. Click **Modify model access** / **Enable specific models**.
4. Fill in the use-case details form when prompted (company/individual name, website or
   "N/A", and a short use-case description — "Monitoring public vendor and regulatory
   sources to notify a builder when changes affect systems they operate" is accurate).
5. Select **Anthropic → Claude Haiku 4.5** and **Claude Sonnet 4.5**, then submit.
6. Access for Anthropic models is usually granted immediately.

Verify:

```bash
.venv/bin/python -c "
import boto3
r = boto3.client('bedrock-runtime', region_name='us-east-1').converse(
    modelId='us.anthropic.claude-haiku-4-5-20251001-v1:0',
    messages=[{'role':'user','content':[{'text':'Say OK'}]}],
    inferenceConfig={'maxTokens':5})
print(r['output']['message']['content'][0]['text'], r['usage'])"
```

Until this clears, the real-model path cannot be exercised, demoed, or recorded.

### 2. Repository must become public

Rules require a public repo. Flip it in **Settings → General → Danger Zone → Change
visibility** before 14 Sep. Nothing in the repo contains credentials — `.gitignore`
excludes `data/`, `*.db` and `.env*`, and no AWS keys are committed.

### 3. Demo video

Five minutes maximum, must show the working project and pitch the problem, audience, and
why it matters.

Draft beat sheet:

| Time | Beat |
|---|---|
| 0:00–0:35 | The problem. "I've built eleven things this year. I could not tell you which of them still comply with anything." |
| 0:35–1:05 | `builtwatch system add "..."` — plain text becomes a passport, with unknowns preserved rather than guessed |
| 1:05–1:25 | `builtwatch source list` — coverage is explicit, not "we watch everything" |
| 1:25–2:40 | `builtwatch scan` — one affected system with a cited passage, one explicitly unaffected, one insufficient-information |
| 2:40–3:05 | A failed source shown as a **coverage failure**, not silence |
| 3:05–3:35 | Re-run the scan: silent. No duplicate alerts. |
| 3:35–4:15 | `builtwatch finding export` — the saved handoff file, opened |
| 4:15–5:00 | Architecture: two-stage screening, read-only tools, grounding validation, cost ceilings |

## Post-submission

Judging runs to 8 October. Keep the deployed demo (if any) and the repo public and stable
through that window.
