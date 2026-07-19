# Cloud Run Local Source Pipeline

This document describes how to deploy the Omega V5 dashboard and API to Google
Cloud Run directly from your local source code.

## Deploy

The `deploy_dashboard_cloud_run.ps1` script provides a safe, interactive way to
deploy the application. It will ask for confirmation before starting.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\cloud\deploy_dashboard_cloud_run.ps1
```

The script submits this directory with `.gcloudignore`, builds `Dockerfile`, pushes
the image to Artifact Registry, deploys Cloud Run, and checks `/health` with an
identity token.

## Optimizing Uploads

The `gcloud run deploy` command uploads the entire directory (respecting
`.gcloudignore`) to Cloud Build. To accelerate deployments, it is critical to
keep this upload context small.

The `.gcloudignore` file should exclude:

- Local artifacts (`out/`, `cache/`, `logs/`)
- Python caches (`__pycache__/`)
- Node.js dependencies (`node_modules/`)
- Git history (`.git/`)
- Local environment files (`.env`)

## Python Dependency Management

To ensure reproducible and secure builds, Python dependencies are managed with
`pip-tools`.

- `requirements.in`: This file lists the direct, top-level dependencies.
- `requirements.txt`: This is a lock file generated from `requirements.in`. It
  contains the complete list of pinned and hashed dependencies.

To update dependencies, edit `requirements.in` and run `pip-compile requirements.in`.
## Conflict-Free Updates

Do not use floating production dependencies such as `pnpm@latest`. The deployment
process pins versions for `node` and `pnpm` to ensure reproducible builds.
Before changing dependency versions, run the compatibility check script:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\cloud\check_dependency_compat.ps1
```
