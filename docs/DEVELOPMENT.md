# Development and release

The working checkout for the October 17 release is
`/Users/kelvinling/Downloads/BuiltWatch`. The older `/Users/kelvinling/BuiltWatch`
checkout and its nested `site-source` are historical checkouts. Work from this repository's
root; do not edit two copies and assume they synchronize.

The Sites source helper opens and packages the existing project declared in
`.openai/hosting.json`. Preserve that project ID, the public audience and existing
runtime secrets. The public GitHub repository carries the application source and CI.

## Offline validation

Use Python 3.12 or later and Node 22 or later:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
npm ci
.venv/bin/ruff check src tests infra scripts
.venv/bin/pytest -q
.venv/bin/python -m builtwatch.evaluation
npm run check
npm test
npm run build
```

Tests stub AWS/model calls. The rules benchmark is committed and deterministic. Runtime
JavaScript tests start local test servers; restricted environments need localhost access.
GitHub Actions runs these gates on pushes and pull requests without AWS credentials.

## Deployment

AWS changes and the web gateway are separate deployments. Read OPERATIONS.md. Use the
existing AWS account and update-only package rollout; never use legacy single-owner
provisioning scripts for an account backend upgrade. Preserve IAM-only function URLs,
Bedrock denial, zero model ceilings, schedules, concurrency and tenant records. Back up
current packages/configuration in ignored private `data/` before updating.

Package the exact pushed Sites source and deploy its saved version. Verify the deployed
code hashes, public page/assets/API, anonymous workspace rejection, and a controlled
rules-only scan. Report browser/authentication verification limits explicitly.
