# Using BuiltWatch

Open https://builtwatch.kelvinlingac.chatgpt.site/ and choose **Open your workspace → Sign in with ChatGPT**. Use the same ChatGPT account on every visit. The site's access policy must allow visitors before other professionals can sign in; account support does not itself make the site public.

1. Confirm the header says **Private workspace**. Anonymous visitors see historical sample data, not a live personal workspace.
2. Choose **Add a system**. Describe what it does, paste a summary from your builder agent, or load a short README. Choose **Prepare my profile**, then review the extracted draft. Fill any useful gaps or leave them unknown. **Save and start watching** saves your confirmed profile and starts the first check. Do not include credentials or customer records. The optional detailed editor requires no model call.
3. Open **Check history → Check now → Start check**. Status updates while the page is open; the job continues if you leave. Records remain readable during the check. Editing waits until it finishes.
4. Open **Needs attention**. Read the evidence, the system facts, uncertainties, and suggested review. Check **Watched sources** for gaps. An interrupted check is not an all-clear.
5. Choose **Review with my agent → Copy for my agent** and paste the result into your existing builder conversation. Evidence and source dates travel with it. Markdown download remains available. Nothing is sent or changed automatically.
6. Use **Update from a summary** as your system changes; review the proposed update before saving. The account menu lets you pause or enable daily checks (7 a.m. America/Toronto). Findings are delivered in the web UI, not by email or push.

## Account boundary

The Sites dispatcher supplies verified, site-scoped ChatGPT identity headers. The server Worker hashes the stable identifier and signs each AWS request with HMAC-SHA256, binding method, path, body, account, timestamp and nonce. The browser never receives the signing secret and cannot select the account partition. AWS rejects expired/replayed signatures. Cross-origin writes are rejected by the Worker. ChatGPT accounts are required; independent password signup is not provided.

All user records are keyed within a fixed DynamoDB account partition. API writes and background workers use expiring conditional locks. A separate worker allows reads during checks. The operational directory contains account hashes only. Public source snapshots are also partitioned because their observation histories differ per workspace.

## Hosting and cost

The website and sign-in gateway run on Sites (Cloudflare Workers). DynamoDB, Lambda, EventBridge Scheduler and Strands/Amazon Bedrock run in the owner's AWS account, us-east-1 (Nova uses US inference profiles). No database or application server is kept running continuously.

The pilot admits 25 workspaces, with 10 systems each and five agent-prepared drafts per day. Shared edge request counters and AWS IAM protect the API from unrestricted direct invocation. Model thresholds: $0.25/run, $0.50/day, $2/month. The shared pilot allowance reserves $1 before a worker can start and releases the unused portion when it finishes, against $10/month. A timed-out job retains its full reservation. These are conservative model estimates, not an AWS billing hard cap. In-flight model calls can overshoot the per-run threshold; infrastructure charges are separate. The owner pays; there is no billing or payment collection from users.

## Operations and limits

- DynamoDB point-in-time recovery retains seven days. Lambda logs retain seven days. Secrets live in Sites/Lambda runtime settings and ignored local operator files.
- Daily jobs are queued asynchronously, with bounded worker concurrency and job age. Duplicate jobs do not re-run completed checks. Source failures and aborted assessments remain visible.
- Website deployment does not widen the Sites access policy. Public access needs explicit authorization.
- The owner inventory was copied to the uniquely verified owner account while Site access remained owner-only, and counts were verified. The original SQLite database remains preserved in private S3. The legacy daily schedule was disabled with user approval after verification; the new account schedule remains enabled.
- This is an early production pilot, not an unrestricted commercial service: curated coverage, small allowances, no team sharing, no email notifications, no service-level commitment, and no independent penetration test.
- Before a wider launch, verify sign-in with a second real ChatGPT account and conduct browser/mobile acceptance testing. Offline and HTTP tests do not establish those results.

## Deploy and rollback

`infra/deploy_accounts.py --build-only` packages dependencies and application source. Running it without that flag deploys the package to the explicitly checked AWS account. Both functions use `accounts_runner.lambda_handler`; only the API receives the signing secret. The worker receives model permissions; the API does not. Set Sites `BW_API_URL` and secrets `BW_PROXY_SECRET`, `BW_AWS_ACCESS_KEY_ID`, `BW_AWS_SECRET_ACCESS_KEY`, then build/package/deploy the exact source using Sites.

Retain the previous saved Sites version for UI rollback. Do not run the legacy `deploy_web.py` as a new-account deployment: it configures the old shared-key service. Keep the legacy S3 database until migration is verified. Restoring DynamoDB creates a new table; update the Lambda table setting only after validating the restore.
