# BuiltWatch security boundaries

Public source is intentional. Security must not depend on hidden URLs, AWS resource names, model prompts, account IDs, or quota constants.

- AWS function URLs require IAM authorization. The website service identity can invoke only the current API URL; it cannot access models, databases or storage directly. HMAC additionally binds verified account, method, path, body, timestamp and replay nonce.
- Independent Cognito registration uses a confidential client; its secret is stored only as a server runtime secret. Public code cannot use it to bypass registration limits. Passwords and codes must never be logged.
- Browser sessions use 256-bit random tokens with only their hashes in D1. Cookies are Secure, HttpOnly, SameSite=Lax, host-only, and expire after seven days. State-changing browser requests require same-origin headers. ChatGPT/caller account headers no longer authenticate users.
- Agent tokens are random, hashed, revocable, expire after 90 days and are restricted to one profile plus its findings. They cannot trigger model calls. Daily sync limits apply centrally.
- Profiles and findings are partitioned by verified account. Sources are curated, retrieval is bounded, agent tools are read-only, and grounding validation rejects unsupported claims. Imported text is untrusted data.
- Anonymous demo actions execute locally. They never invoke paid services. The offline demo is self-contained and contains only public example data and browser code.
- `data/`, environment files, dependencies, caches, private keys and generated builds are ignored by Git. Do not commit connection setup prompts, user profiles, credentials, deployment access files or customer data. Rotate any exposed secret; deleting it from a later commit is insufficient.

The 12 September 2026 release audit checked all reachable historical Git blobs for
current deployment credentials, AWS access-key identifiers, private keys and GitHub token
patterns. No matches were found. `npm audit --omit=dev` currently reports no production
vulnerabilities; Python dependency auditing is not installed in the local environment.
This bounded audit and the automated tests do not replace an independent penetration test
or guarantee absence of all vulnerabilities. Security issues should be reported privately
to the repository owner; do not include exploit credentials or user data in public issues.

Business, Operations and Technical are presentation views, not authorization roles.
The server accepts only those preference values and preserves monitoring settings.
An agent connection cannot set account preferences or obtain owner privileges.
The additional business-news source is a fixed registry URL; no URL from an import,
user profile, article or model response is followed.
