# DeFi Docker Build + Cloud Run + Firebase + Cloud SQL Skill

## Purpose
This skill standardizes how to build, deploy, and operate DeFi services using:
- **TypeScript** services
- **Docker** image builds
- **Google Cloud Run** deployments
- **Firebase** integrations (Auth, Firestore, Functions/SDK usage as needed)
- **Cloud SQL** for relational persistence

Use this as the default blueprint for new services and production rollouts in this repository.

---

## 1) Reference Architecture

### Runtime
- Service: Node.js (TypeScript) containerized with Docker
- Platform: Cloud Run (managed)
- Database: Cloud SQL (PostgreSQL recommended for DeFi index/state workloads)
- Identity & client integration: Firebase Auth
- Optional event/state layer: Firestore for realtime UI state mirrors

### High-level flow
1. Client authenticates via Firebase Auth.
2. API receives bearer token and verifies Firebase JWT.
3. API reads/writes transactional state in Cloud SQL.
4. API emits denormalized views to Firestore (optional) for frontend realtime UX.
5. Service is built by Docker and deployed to Cloud Run revisions.

---

## 2) Required GCP/Firebase Setup

### Enable APIs
- Cloud Run Admin API
- Artifact Registry API
- Cloud Build API
- Secret Manager API
- Cloud SQL Admin API
- IAM Service Account Credentials API
- Firebase Management (if provisioning is needed)

### Service accounts
Create least-privilege service accounts:
- **runtime SA** (attached to Cloud Run service)
- **deploy SA** (used by CI/CD)

Grant minimum roles:
- Runtime SA:
  - `roles/cloudsql.client`
  - `roles/secretmanager.secretAccessor`
  - logging/monitoring write roles as needed
- Deploy SA:
  - `roles/run.admin`
  - `roles/iam.serviceAccountUser` (on runtime SA)
  - `roles/artifactregistry.writer`
  - `roles/cloudbuild.builds.editor` (if using Cloud Build)

### Network/security
- Prefer private IP connectivity to Cloud SQL where feasible.
- Restrict ingress on Cloud Run (internal + LB where required).
- Store all sensitive values in Secret Manager.

---

## 3) Environment Contract (Do Not Inline Secrets)

Required env vars (example contract):
- `NODE_ENV=production`
- `PORT=8080`
- `GCP_PROJECT_ID`
- `FIREBASE_PROJECT_ID`
- `CLOUD_SQL_CONNECTION_NAME` (`project:region:instance`)
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD` (from Secret Manager)
- `DATABASE_URL` (optional consolidated DSN)
- `JWT_AUDIENCE` (if validating custom audience)

Recommended DeFi env vars:
- `CHAIN_ID`
- `RPC_URL` (from Secret Manager)
- `INDEXER_START_BLOCK`
- `CONFIRMATION_DEPTH`
- `FEATURE_FLAG_REORG_PROTECTION=true`

---

## 4) Docker Build Standard

### Dockerfile template (Node + TS)
```dockerfile
# syntax=docker/dockerfile:1
FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /app/dist ./dist
EXPOSE 8080
CMD ["node", "dist/index.js"]
```

### Build command examples
```bash
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/$GCP_PROJECT_ID/omega-apex/api:$COMMIT_SHA
```

Best practices:
- Pin Node major version.
- Keep image minimal and non-root where possible.
- Avoid build-time secret injection.
- Use immutable image tags (`$COMMIT_SHA`) plus optional channel tags (`staging`, `prod`).

---

## 5) Cloud SQL Connection Pattern

### Cloud Run native connector (recommended)
Deploy with:
- `--add-cloudsql-instances $CLOUD_SQL_CONNECTION_NAME`

For Postgres via Unix socket:
- socket path: `/cloudsql/$CLOUD_SQL_CONNECTION_NAME`

Example DSN:
```txt
postgresql://DB_USER:DB_PASSWORD@/DB_NAME?host=/cloudsql/CLOUD_SQL_CONNECTION_NAME
```

### App-level recommendations
- Use pooled connections with conservative limits on Cloud Run concurrency.
- Enforce statement timeout.
- Run migrations as a separate controlled step/job, not on every boot.

---

## 6) Firebase Integration Standard

### Auth verification
- Verify Firebase ID token on every protected request.
- Map UID to internal user/account records in Cloud SQL.
- Enforce token revocation strategy for high-risk actions.

### Firestore usage (optional)
- Keep authoritative financial state in Cloud SQL.
- Publish read-optimized projections to Firestore for realtime clients.
- Never treat Firestore projection as settlement source of truth.

---

## 7) Cloud Run Deploy Standard

### Deploy command template
```bash
gcloud run deploy omega-apex-api \
  --image us-central1-docker.pkg.dev/$GCP_PROJECT_ID/omega-apex/api:$COMMIT_SHA \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --service-account runtime-omega-apex@$GCP_PROJECT_ID.iam.gserviceaccount.com \
  --add-cloudsql-instances $CLOUD_SQL_CONNECTION_NAME \
  --set-env-vars NODE_ENV=production,PORT=8080,GCP_PROJECT_ID=$GCP_PROJECT_ID,FIREBASE_PROJECT_ID=$FIREBASE_PROJECT_ID,DB_NAME=$DB_NAME,DB_USER=$DB_USER,CLOUD_SQL_CONNECTION_NAME=$CLOUD_SQL_CONNECTION_NAME \
  --set-secrets DB_PASSWORD=DB_PASSWORD:latest,RPC_URL=RPC_URL:latest \
  --min-instances 0 \
  --max-instances 20 \
  --concurrency 40 \
  --cpu 1 \
  --memory 512Mi \
  --timeout 300
```

Tune per workload:
- Event ingestion/indexing APIs: lower concurrency, higher memory.
- Read-heavy APIs: moderate concurrency and autoscaling ceiling.

---

## 8) CI/CD Blueprint (GitHub Actions)

```yaml
name: build-and-deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write

    steps:
      - uses: actions/checkout@v4

      - name: Authenticate to Google Cloud (OIDC)
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
          service_account: ${{ secrets.GCP_DEPLOY_SA }}

      - name: Setup gcloud
        uses: google-github-actions/setup-gcloud@v2

      - name: Configure Artifact Registry auth
        run: gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

      - name: Build and push image
        env:
          GCP_PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
        run: |
          IMAGE="us-central1-docker.pkg.dev/$GCP_PROJECT_ID/omega-apex/api:${GITHUB_SHA}"
          docker build -t "$IMAGE" .
          docker push "$IMAGE"
          echo "IMAGE=$IMAGE" >> $GITHUB_ENV

      - name: Deploy to Cloud Run
        env:
          GCP_PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
          FIREBASE_PROJECT_ID: ${{ secrets.FIREBASE_PROJECT_ID }}
          DB_NAME: ${{ secrets.DB_NAME }}
          DB_USER: ${{ secrets.DB_USER }}
          CLOUD_SQL_CONNECTION_NAME: ${{ secrets.CLOUD_SQL_CONNECTION_NAME }}
        run: |
          gcloud run deploy omega-apex-api \
            --image "$IMAGE" \
            --region us-central1 \
            --platform managed \
            --allow-unauthenticated \
            --service-account "runtime-omega-apex@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
            --add-cloudsql-instances "$CLOUD_SQL_CONNECTION_NAME" \
            --set-env-vars "NODE_ENV=production,PORT=8080,GCP_PROJECT_ID=$GCP_PROJECT_ID,FIREBASE_PROJECT_ID=$FIREBASE_PROJECT_ID,DB_NAME=$DB_NAME,DB_USER=$DB_USER,CLOUD_SQL_CONNECTION_NAME=$CLOUD_SQL_CONNECTION_NAME" \
            --set-secrets "DB_PASSWORD=DB_PASSWORD:latest,RPC_URL=RPC_URL:latest"
```

---

## 9) DeFi-Specific Reliability Controls

- Idempotent transaction/event processing keys.
- Reorg-aware indexing with confirmation depth gating.
- Dead-letter strategy for failed chain/event jobs.
- Circuit breakers for RPC instability.
- Deterministic decimal/math handling (no floating-point finance math).
- Backfill tooling separated from online request path.

---

## 10) Observability + SLOs

Track at minimum:
- Request latency (p50/p95/p99)
- Error rate by route
- DB connection pool saturation
- RPC call failure rate + timeout rate
- Index lag (latest chain block - processed block)

Operational alerts:
- Sustained 5xx > threshold
- Index lag above threshold window
- Cloud SQL connection exhaustion

---

## 11) Rollback & Release Strategy

- Use Cloud Run revisions for safe rollback.
- Progressive rollout (e.g., 5% canary -> 50% -> 100%).
- Keep DB migrations backward-compatible for at least one deploy window.
- Tag every deployment with commit SHA and release notes.

Rollback command:
```bash
gcloud run services update-traffic omega-apex-api \
  --region us-central1 \
  --to-revisions PREVIOUS_REVISION=100
```

---

## 12) Security Checklist

- [ ] No secrets committed to repo
- [ ] Principle of least privilege for service accounts
- [ ] Token verification on all protected routes
- [ ] Input validation on all external payloads
- [ ] Dependency and container image scanning enabled
- [ ] Audit logging enabled for admin/deploy actions

---

## 13) Done Criteria for New Service

A service is production-ready only if:
1. Docker build is reproducible and pinned.
2. Cloud Run deploy is automated via CI/CD.
3. Cloud SQL connectivity is stable under load test.
4. Firebase Auth validation is enforced.
5. Secrets are exclusively sourced from Secret Manager.
6. SLO dashboards + alerts are live.
7. Rollback rehearsal has been executed at least once.
