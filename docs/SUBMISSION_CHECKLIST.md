# Submission checklist — Agents for Humans

**Submission closes: 14 September 2026, 17:00 PT.**
Judging: 15 September – 8 October 2026. Winners: 14 October 2026.

## Hackathon requirements

> **Verified against live state on 10 September 2026.** Every ✅ below was checked
> against the running system, not assumed. Known-open defects are tracked separately in
> [ISSUES.md](ISSUES.md) — read that before submitting, since BW-3 (private repo) is a
> hard blocker and BW-5 (demo domain) affects how this is judged.

| Requirement | Status | Notes |
|---|---|---|
| Built with Strands Agents SDK | ✅ | `strands-agents 1.54.0`; two agent stages, custom tools, hook-based budget guards |
| AWS account | ✅ | `[aws-account-redacted]`, AdministratorAccess via IAM Identity Center (SSO profile `[aws-profile-redacted]`). *Superseded `561217459367`; nothing runs there.* |
| AWS Builder ID | ✅ | Kelvin Ling / `[owner-email-redacted]` |
| $50 AWS credits requested | ✅ | Submitted before the 11 Sep 12:00 PT cutoff |
| Public code repository | ⛔ **BLOCKER** | Verified private (`api.github.com` → 404) on 10 Sep 2026. Rules require public with an OSI licence. **Flip before 14 Sep 17:00 PT.** |
| MIT or Apache license | ✅ | [MIT](../LICENSE) + [NOTICE](../NOTICE) |
| README | ✅ | [README.md](../README.md) |
| Architecture diagram | ✅ | [ARCHITECTURE.md](ARCHITECTURE.md) — Mermaid, renders on GitHub |
| Demo video ≤ 5 min | ⬜ **OUTSTANDING** | Beat sheet below. **Kelvin must record and narrate.** |
| Text description of features | ⬜ | Draft from README once the demo is final |
| Functioning end-to-end agent | ✅ | Running in production on Amazon Nova (`nova-lite` screen / `nova-pro` assess). Two tenants have completed scans end to end. *Anthropic models are not entitled on this account; the model ladder fell back automatically.* |
| AI assistance disclosed | ✅ | [NOTICE](../NOTICE) and README |
| Newly created in submission period | ✅ | First commit 8 Sep 2026; no prior code incorporated |
| Live demo link *(bonus)* | ⚠️ | Live and returning 200: `https://builtwatch.kelvinlingac.chatgpt.site`. **A ChatGPT-branded domain for an AWS competition — see BW-5.** `builtwatch.org`/`.com` unregistered. |
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

The account has never accepted Anthropic's model terms, so Anthropic models return
`ValidationException: Error 002`. **This is not a blocker.** The model ladder in
`config.py` falls back automatically and the system has been running in production on
Amazon Nova (`nova-lite` screening, `nova-pro` assessment) since 9 September.

Pursuing Anthropic access is a **quality upgrade, not a fix**: the grounding rules lean on
instruction-following, and Nova has been observed fabricating quotes (~2 in 57 assessments;
the validator catches them, but a downgraded answer still costs a model call).

**If you want it — console, ~3 minutes, account owner only** (it is an acceptance of model
provider terms, so no agent can do it):

1. Sign in to the console for account `[aws-account-redacted]`, region **us-east-1**.
2. Go to **Amazon Bedrock → Model catalog**. *(The old "Model access" page has been
   retired — serverless models now enable on first invocation, but Anthropic still
   requires the one-time use-case form.)*
3. Filter provider → **Anthropic**, pick **Claude Haiku 4.5**, choose **Open in
   Playground**. For a first-time user this opens the use-case form instead.
4. Fill it in — "Individual / independent developer" and `N/A` for a website are accepted.
   Use case: *"Monitoring public vendor policy, API, and regulatory sources to notify a
   builder when external changes affect software systems they operate."*
5. Submit, then send one playground message — that first invoke enables it account-wide.

Then confirm and let the ladder pick it up automatically:

```bash
export AWS_PROFILE=[aws-profile-redacted] AWS_REGION=us-east-1
eval "$(aws configure export-credentials --format env)"
.venv/bin/builtwatch doctor
```

`doctor` probes each model with a real one-token call and prints the cheapest working pair.
Trust it over `ListFoundationModels`, which lists models the account cannot invoke.

## 2. Repository must become public

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
| 0:35–1:10 | Web workspace: paste a plain-text description → the Strands intake agent drafts a passport. **Show unknowns preserved rather than guessed.** |
| 1:10–1:30 | Source registry — coverage is explicit and enumerable, not "we watch everything" |
| 1:30–2:45 | A completed check: one affected system with its cited passage and matched passport fact, one explicitly unaffected, one insufficient-information |
| 2:45–3:10 | A failed source shown as a **coverage failure**, not silence *(the real Gmail `ReadTimeout` from 9 Sep is a genuine example)* |
| 3:10–3:35 | Re-run: quiet. No duplicate alerts, and $0.00 because nothing changed. |
| 3:35–4:10 | Export the builder handoff — a saved file, not chat text |
| 4:10–5:00 | Architecture: two-stage Nova screening/assessment, read-only Strands tools, grounding validation that downgrades ungrounded claims, and the spend ceilings that abort rather than degrade |

**Record from the web workspace, not the CLI** — the CLI beat sheet this replaced predates
the UI. Keep the CLI for the architecture beat if it helps show the internals.

## Post-submission

Judging runs to 8 October. Keep the deployed demo (if any) and the repo public and stable
through that window.