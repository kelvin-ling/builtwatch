# Independent registration and durable demo

The current release replaces ChatGPT sign-in with AWS Cognito email/password registration. The frontend remains a thin Sites/Cloudflare gateway; AWS owns identity, agent execution and inventory/findings storage. See [ACCOUNTS.md](ACCOUNTS.md) for the authoritative current workflow, limits, agent connection contract and operator pause controls. Earlier architecture decisions below are historical and superseded where they mention ChatGPT sign-in or read-only demos.

The public demo performs local edits and historical replay only. It is independent of live allowances and includes a downloadable offline copy. Anonymous users cannot cause a model call. The daily agent integration is a pull/sync mechanism initiated by a user-authorized builder; it never claims to wake an unsupported agent.

Current registration adds a 100 lifetime-attempt ceiling, 200 global authentication attempts/day, 20 verification/recovery requests/day, and a confidential Cognito client. Existing 25-workspace admission and shared model reservations remain. Email verification is required. Owner migration is restricted to the configured verified email and previously verified tenant.

---

# Public pilot design

User authorization: the user explicitly approved public deployment once ready. Earlier handoff notes saying public approval is pending are superseded. Deployment still requires a valid AWS operator session and successful live checks.

## Minimal onboarding

1. Open the site and sign in with ChatGPT. Each account receives its own private workspace, subject to pilot capacity.
2. Select **Add a system**. Describe it in one sentence, paste a builder's summary, or load a short README/text file.
3. **Prepare my profile** runs a bounded Strands intake agent using Nova Lite. The agent extracts only supported details; missing facts remain unknown. It has no repository credentials, URL-fetch tools, or ability to change the app.
4. **Review profile → Save and start watching** confirms the draft, saves it in AWS, and queues the first check. The optional detailed editor and JSON import remain available.
5. For a finding, **Review with my agent → Copy for my agent** produces a review request with evidence and source dates. Paste it into the existing project conversation. Markdown download remains available. No data is automatically sent to another agent.

An alternate entry route asks the builder agent to inspect its existing project context and provide a plain-language summary. The user copies that answer into BuiltWatch; no schema or long questionnaire is required.

## Why these models

Use Nova Lite for intake and inexpensive initial relevance screening. Keep Nova Pro for the deeper assessment and existing grounding checks. This is a conservative continuation of the tested pipeline, not a claim of benchmark superiority. Intake does not need the more expensive assessment model.

Bedrock model use is metered. AWS promotional credits may offset a bill, but are not permanent free inference. Cloudflare Workers AI has a limited daily free allowance (10,000 neurons); some models require a paid Workers plan. That allowance could support experimentation, but switching the core agent there would add another model provider and weaken the AWS focus without removing the need for quotas. Local open models also require compute and operations. Sample browsing, copy handoffs, manual profile editing, and completed unchanged source/profile pairs require no new model calls.

References:
- https://aws.amazon.com/bedrock/pricing/
- https://developers.cloudflare.com/workers-ai/platform/pricing/
- https://agentsforhumans.devpost.com/rules

## Hosting decision

Keep AWS as the application platform: Strands, Nova/Bedrock, Lambda API and workers, DynamoDB user records, and EventBridge checks. The existing Sites/Cloudflare layer serves the small web app and verified ChatGPT sign-in. One small D1 table counts requests before they reach AWS; it contains no profiles or findings.

A complete move of the front end to AWS is possible, but is not a prerequisite for public access or the competition. It would also require replacing the existing sign-in flow and migrating identities. Retaining the thin existing gateway avoids that churn for this launch. The rules require Strands; AgentCore is encouraged, not mandatory. ChatGPT accounts are required for the current sign-in flow; passwords are not handled by BuiltWatch.

## Cost controls

- 25 active pilot workspaces, enforced centrally before serving account API operations; existing owner enrollment must be seeded before public launch.
- 10 systems per workspace; five agent-prepared drafts per day; a repeated identical pending draft is reused.
- Edge traffic: 180 account API requests/minute and 10,000/day globally; 300/day/account. Limits are shared across gateway instances through D1. Missing/broken counters fail closed. These may temporarily pause access during a spike; saved data is retained.
- Current and retired Lambda URLs require AWS IAM authentication after the rollout. A dedicated gateway principal has only URL-invoke permission on the current API. The separate HMAC binds each request to its verified user, path, body and nonce. Browser users never receive either signing credential.
- Shared $10/month model reservations. Per-account thresholds: $2/month, $0.50/day, $0.25/check; intake has a $0.02 run threshold. In-flight calls may overshoot thresholds; timed-out jobs retain conservative shared reservations.
- Two background workers and four API executions maximum. No always-on servers. No automatic increase of limits or paid plans.
- AWS budget alerts remain a backstop, not an instantaneous billing kill switch. Infrastructure, storage and edge service policies are separate from model estimates. Do not promise an exact maximum AWS bill.

## Release steps

1. Run Python and Node/runtime tests; build the AWS package.
2. Renew AWS SSO if needed. Deploy account API/worker changes and seed an enrollment seat for the migrated owner.
3. Run `infra/protect_api.py` to provision a narrowly scoped invoke-only gateway identity. Store its credentials as Sites secrets `BW_AWS_ACCESS_KEY_ID` and `BW_AWS_SECRET_ACCESS_KEY`; retain `BW_API_URL` and `BW_PROXY_SECRET`.
4. Build and privately deploy the site with the D1 migration. Verify the real signed gateway and live intake extraction.
5. Run `infra/protect_api.py --enable` to require IAM on the current and retired function URLs. Verify direct anonymous requests return 403 and the gateway still works.
6. Apply the user's approved public access change to the existing site and verify anonymous sample/API behavior. Preserve the site URL and owner data.

Rotate gateway credentials by creating a replacement key, updating Sites secrets, deploying and verifying, then deleting the previous key. Never print or commit credentials. `data/accounts-access.json` is private operator material.
