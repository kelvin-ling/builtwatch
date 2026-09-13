# Submission checklist — Agents for Humans

**Submission closes: 14 September 2026, 17:00 PT.**
Judging: 15 September – 8 October 2026. Winners: 14 October 2026.

## Hackathon requirements

> **Verified against live state on 13 September 2026.** Every ✅ below was checked
> against the running system, not assumed. Known-open defects are tracked separately in
> [ISSUES.md](ISSUES.md) — read that before submitting, since BW-3 (private repo) is a
> hard blocker and BW-5 (demo domain) affects how this is judged.

| Requirement | Status | Notes |
|---|---|---|
| Built with Strands Agents SDK | ✅ | `strands-agents 1.54.0`; two agent stages, custom tools, hook-based budget guards |
| AWS account | ✅ | `[aws-account-redacted]`, AdministratorAccess via IAM Identity Center (SSO profile `[aws-profile-redacted]`). *Superseded `561217459367`; nothing runs there.* |
| AWS Builder ID | ✅ | Kelvin Ling |
| $50 AWS credits requested | ✅ | Submitted before the 11 Sep 12:00 PT cutoff |
| Public code repository | ⛔ **BLOCKER** | Still private — re-verified `api.github.com` → 404 on **13 Sep 2026**. Rules require public with an OSI licence. **Flip before 14 Sep 17:00 PT or the submission is invalid.** See the history note below first. |
| MIT or Apache license | ✅ | [MIT](../LICENSE) + [NOTICE](../NOTICE) |
| README | ✅ | [README.md](../README.md) |
| Architecture diagram | ✅ | [ARCHITECTURE.md](ARCHITECTURE.md) (Mermaid, verified to render) and [architecture.png](architecture.png), embedded in the README and ready for the Devpost gallery |
| Demo video ≤ 5 min | ✅ produced · ⬜ **upload** | Refined 13 Sep to cover every required element (see *Demo video* below). **Upload to YouTube or Vimeo as public**, which the rules require. |
| Text description of features | ✅ | [DEVPOST_SUBMISSION.md](DEVPOST_SUBMISSION.md), section by section for the Devpost form |
| Functioning end-to-end agent | ✅ | Running in production on Amazon Nova (`nova-lite` screen / `nova-pro` assess). Two tenants have completed scans end to end. *Anthropic models are not entitled on this account; the model ladder fell back automatically.* |
| AI assistance disclosed | ✅ | [NOTICE](../NOTICE) and README |
| Newly created in submission period | ✅ | First commit 8 Sep 2026; no prior code incorporated |
| Live demo link *(bonus)* | ✅ | `https://builtwatch.org` — registered, deployed and returning 200. The generated Sites hostname redirects to the custom domain, and `https://www.builtwatch.org/` is configured in Cloudflare and verified to return a permanent redirect to the apex (13 Sep 2026). |
| builder.aws blog post *(bonus)* | ⬜ | Up to +0.6 (0.2 × 3 posts) |

## Historical provider-access note

Earlier diagnostic output said some provider models were unavailable:

```
ValidationException: Error 002: Access to Bedrock models is not allowed for this account
```

This was **not an IAM problem**. The AWS account has AdministratorAccess and the
control plane works correctly:

```
get_use_case_for_model_access  → ResourceNotFoundException:
    "You have not filled out the request form. Fill out the form before getting access."

anthropic.claude-sonnet-4-5   agreement=NOT_AVAILABLE  entitlement=AVAILABLE  auth=AUTHORIZED
amazon.nova-lite-v1:0         agreement=AVAILABLE      entitlement=AVAILABLE  auth=AUTHORIZED
```

The account has not accepted Anthropic's model terms, so Anthropic models can return
`ValidationException: Error 002`. **This is not a blocker.** The model ladder falls back
automatically and production runs on Amazon Nova (`nova-lite` screening, `nova-pro`
assessment).

Pursuing Anthropic access is optional quality work, not a release requirement: grounding
validation still catches unsupported quotes and downgrades the result when needed.

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

## Remaining submission blockers

### Repository must become public

Rules require a public repo. Flip it in **Settings → General → Danger Zone → Change
visibility** before 14 Sep. The working tree contains no credentials, private databases,
recordings, or personal owner addresses — `.gitignore` excludes `data/`, `*.db`, `.env*`,
and competition recordings. Before changing visibility, review the complete commit history:
older pre-sanitization commits contain owner email references and must be scrubbed or
replaced with a clean public history. Do not force-push that rewrite until the repository
has been backed up.

Verified 13 September 2026: the two owner addresses appear 23 times in commit *contents*
(introduced in `a89c671`, `7453039` and `5008376`; removed from the tree in `ff739d6`).
Commit author and committer metadata already use the GitHub noreply address. A full-history
scan found no AWS keys, private keys, bearer tokens, Cognito client secret, owner token or
account password. Publishing the history as-is exposes only those two email addresses; that
is the owner's call.

### Demo video

Rules: at most five minutes, uploaded to YouTube or Vimeo and public, showing the working
project and pitching (1) the problem, (2) who it is for and (3) why it matters. Slides,
screen recordings and voice-over are all acceptable.

The refined cut (13 September 2026) lives in the private media folder, outside this
repository:

| File | Use |
|---|---|
| `BuiltWatch-submission-video-subtitle-ready.mp4` | Captions burned in, no audio. Record your voice-over over this one. |
| `BuiltWatch-submission-video-narrated.mp4` | The same cut with synthetic narration. Submit this if there is no time to record. |
| `TRANSCRIPT-submission.md` | Timed script for reading the voice-over. |

| Requirement | Where it is covered |
|---|---|
| The problem | *The problem* and *Why it stays unsolved* slides |
| Who it is for | *Who it's for*: independent professionals, makers and small teams |
| Why it matters | *Why it matters*: retired API versions, stricter sender rules, exploited vulnerabilities, the EU AI Act Article 50 date |
| Working project | *A real run* (verbatim Bedrock run log) followed by the product walkthrough |
| Strands Agents usage | *How it works* and *Architecture* slides |

## Post-submission

Judging runs to 8 October. Keep the deployed demo (if any) and the repo public and stable
through that window.
