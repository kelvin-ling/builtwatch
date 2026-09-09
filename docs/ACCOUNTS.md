# Using BuiltWatch

Open https://builtwatch.kelvinlingac.chatgpt.site/ . No ChatGPT account is needed.

## Try it without registration

The interactive demo opens immediately. Add an app description, review a locally prepared draft, edit or remove a demo profile, replay the historical example findings, acknowledge/dismiss a result, and copy a builder-agent handoff. Demo changes stay in the current tab and reset on reload. **Reset demo** restores the examples.

The demo uses simple local text matching for drafts and saved real assessments for the original example systems. It does not assess custom demo apps, fetch new developments, call AI, or store your inputs on a server. It remains available when live model, registration, or API limits are reached. **Using BuiltWatch → Download offline demo** saves a standalone file you can open without internet access. Hosting-provider outages or platform-wide quotas can still affect the online page; the downloaded demo is independent.

## Create a private workspace

1. Select **Sign in / Register → Create an account**.
2. Enter your email and a password of at least 12 characters with uppercase, lowercase and a number. No name, company, payment details, AWS account or repository permission is requested.
3. Enter the verification code sent to your email, then sign in. Use **Verify email → Resend code** if needed, or **Forgot password?** to recover access.
4. Look for **Private workspace**. Choose **Add a system**, paste a short description/README/builder summary, and choose **Prepare my profile**. The Strands intake agent prepares a draft; review before **Save and start watching**. Unknown facts stay unknown.
5. Open **Needs attention**, inspect evidence and dates, then **Review with my agent → Copy for my agent**. Paste it into the existing project conversation. Use **Update from a summary** to bring back changes.
6. The account menu controls daily monitoring, agent connections and sign-out. Sign-in lasts seven days; signing in again replaces the previous session. Password recovery invalidates existing web sessions.

The original owner's verified email maps to the previously migrated workspace. This operator-configured exception requires Cognito-verified email ownership. Other accounts receive separate partitions derived from their Cognito subject, never from caller-supplied identity headers.

## Let your builder register the app

1. Open your account and choose **Connect my agent → Create connection**.
2. Copy the private setup instructions into the agent conversation for this app. The agent uses the project context it already has to produce a small profile, avoiding manual form entry.
3. If the agent supports scheduling, the instructions ask it to send the profile and retrieve findings once per UTC day. Otherwise it should sync on request and explain that limitation. BuiltWatch does not wake arbitrary agents itself.
4. The first successful sync registers the app. Later syncs update only that connected app. Check connection status for the last successful sync.
5. Revoke the connection from the account menu whenever needed. Creating a replacement invalidates the previous token. Tokens expire after 90 days.

One active connection per workspace. Its token can update one fixed profile and retrieve that profile's findings; it cannot read other profiles, alter account settings, delete apps or trigger model runs. Syncs use existing daily monitoring and budget limits. The token is shown once, kept only as a hash server-side, and must be stored privately by the agent—not in Git, logs, URLs or shared conversations. No public endpoint accepts arbitrary source URLs.

## Hosting, privacy and limits

AWS Cognito Lite handles registration and passwords. Profiles, findings, source snapshots and checks live in AWS DynamoDB/Lambda/EventBridge; Strands uses Bedrock Nova. The small web gateway runs on Sites/Cloudflare, with D1 request counters, hashed session/connection tokens, account hashes and session email addresses. Passwords pass over TLS to Cognito and are not stored by BuiltWatch. No SMS or paid email sender is enabled.

Registration is capped at 100 lifetime attempts; account API access admits at most 25 workspaces. Authentication is limited to 200 attempts/day globally, 20/hour per IP and 10/hour per email. Verification/recovery requests share 20 email sends/day. These conservative limits may temporarily block legitimate attempts; the demo is unaffected. The server-only Cognito app-client secret prevents direct unauthenticated API use from bypassing this gateway. No public Cognito app client or hosted signup domain is provisioned.

Live account API traffic is limited to 180/minute and 10,000/day globally and 300/day/account. Each workspace supports ten apps and five agent drafts/day. Shared model reservations are $10/month; account thresholds are $2/month, $0.50/day, $0.25/check and $0.02/intake. In-flight calls may overshoot thresholds. Concurrency is four API/two workers. These are model estimates and request controls, not an exact total AWS bill cap. Storage, hosting and provider-level outages/quotas are separate.

This is a bounded public pilot: curated sources, no independent security audit, no team sharing or email finding notifications, and no service-level guarantee. A failed source fetch or interrupted check is shown separately from “nothing relevant found.”

## Operations without code changes

Setting the Sites secret/environment flag `BW_REGISTRATION_ENABLED=false` pauses new registrations. `BW_LIVE_ENABLED=false` pauses proxied AWS operations; static demo assets and local replay stay available. Apply an environment change by deploying the same saved version—no source change is necessary. Existing daily jobs can be paused through the EventBridge schedule without modifying code. Model allowances automatically pause/reopen at their configured periods.

Deploy source using Sites with the included D1 migrations. Runtime secrets are `BW_PROXY_SECRET`, scoped `BW_AWS_ACCESS_KEY_ID` / `BW_AWS_SECRET_ACCESS_KEY`, `BW_COGNITO_CLIENT_ID` / `BW_COGNITO_CLIENT_SECRET`, and the private owner migration mapping. Never publish `data/`. Keep AWS function URLs on `AWS_IAM`; older pre-IAM releases cannot proxy safely. Preserve original S3 backup and keep the old daily schedule disabled.
