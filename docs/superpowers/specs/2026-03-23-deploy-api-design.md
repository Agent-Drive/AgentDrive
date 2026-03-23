# Deploy Agent Drive API to api.agentdrive.so

**Issue:** #8
**Date:** 2026-03-23
**Status:** Approved

## Overview

Deploy the Agent Drive FastAPI application to Google Cloud Run with Cloud SQL (PostgreSQL 16 + pgvector), Secret Manager for credentials, GitHub Actions CI/CD, and custom domain `api.agentdrive.so`.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   GCP: agent-drive-491013                │
│                   Region: us-central1                    │
│                                                          │
│  ┌──────────────┐    ┌──────────────────────────────┐    │
│  │ Artifact     │    │ Cloud Run                    │    │
│  │ Registry     │───▶│ agentdrive-api               │    │
│  │ (Docker)     │    │ - min 0, max 3 instances     │    │
│  └──────────────┘    │ - 1 vCPU, 512MB RAM          │    │
│                      │ - port 8080                   │    │
│                      │ - concurrency: 80             │    │
│                      └──────┬──────┬────────────┘    │    │
│                             │      │                 │    │
│                      ┌──────▼──┐ ┌─▼──────────────┐  │    │
│                      │Cloud SQL│ │ Secret Manager  │  │    │
│                      │pg16 +   │ │ (5 secrets)     │  │    │
│                      │pgvector │ └────────────────┘  │    │
│                      │db-f1-   │                     │    │
│                      │micro    │ ┌────────────────┐  │    │
│                      └─────────┘ │ GCS             │  │    │
│                                  │ agentdrive-files│  │    │
│                                  └────────────────┘  │    │
└─────────────────────────────────────────────────────────┘

DNS (Namecheap):
  api.agentdrive.so  CNAME → ghs.googlehosted.com.
  SSL: Google-managed certificate
```

## Decisions

| Decision | Choice | Reasoning |
|----------|--------|-----------|
| Region | `us-central1` | Cheapest, most services available |
| Database | Cloud SQL PostgreSQL 16 + pgvector | Managed, automatic backups, native Cloud Run integration |
| Secrets | GCP Secret Manager | Best practice, secrets not visible in plaintext |
| CI/CD | GitHub Actions | Config in repo, most common pattern |
| Domain registrar | Namecheap (existing) | Already purchased `agentdrive.so` |
| Cloud Run config | Declarative `service.yaml` | Version-controlled, reviewable, diffable |
| Install script hosting | `/install.sh` route on the API | No extra infra needed |

## Infrastructure Components

### Cloud SQL

- **Instance name:** `agentdrive-db`
- **Version:** PostgreSQL 16
- **Tier:** `db-f1-micro` (shared vCPU, 614MB RAM)
- **Region:** `us-central1`
- **Database:** `agentdrive`
- **Extensions:** `vector` (pgvector)
- **Connection:** Cloud SQL Auth Proxy (built into Cloud Run via connector annotation)
- **No public IP** — private connection from Cloud Run only

### Cloud Run

- **Service name:** `agentdrive-api`
- **Image:** `us-central1-docker.pkg.dev/agent-drive-491013/agentdrive/api:<sha>`
- **Scaling:** 0–3 instances (scales to zero when idle)
- **Resources:** 1 vCPU, 512MB RAM
- **Concurrency:** 80 requests per instance
- **Startup probe:** `GET /health`, 5s initial delay, 5s period, 3 failure threshold
- **Ingress:** All traffic (public API, auth handled by application)
- **Service account:** `agentdrive-api@agent-drive-491013.iam.gserviceaccount.com`

### Secret Manager

```
agentdrive-database-url        # postgresql+asyncpg://user:pass@/agentdrive?host=/cloudsql/...
agentdrive-voyage-api-key      # Voyage AI embedding
agentdrive-cohere-api-key      # Cohere reranking
agentdrive-anthropic-api-key   # Haiku enrichment
agentdrive-workos-api-key      # WorkOS authentication
```

### Plain Environment Variables

```
ENVIRONMENT=production
GCS_BUCKET=agentdrive-files
WORKOS_CLIENT_ID=client_...
```

### Cloud Run Service Config

Declarative config at `cloud-run/service.yaml`:

```yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: agentdrive-api
  annotations:
    run.googleapis.com/ingress: all
spec:
  template:
    metadata:
      annotations:
        run.googleapis.com/cloudsql-instances: agent-drive-491013:us-central1:agentdrive-db
        autoscaling.knative.dev/minScale: "0"
        autoscaling.knative.dev/maxScale: "3"
    spec:
      containerConcurrency: 80
      serviceAccountName: agentdrive-api@agent-drive-491013.iam.gserviceaccount.com
      containers:
        - image: us-central1-docker.pkg.dev/agent-drive-491013/agentdrive/api:latest
          ports:
            - containerPort: 8080
          resources:
            limits:
              cpu: "1"
              memory: 512Mi
          env:
            - name: ENVIRONMENT
              value: production
            - name: GCS_BUCKET
              value: agentdrive-files
            - name: WORKOS_CLIENT_ID
              value: client_PLACEHOLDER
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  key: latest
                  name: agentdrive-database-url
            - name: VOYAGE_API_KEY
              valueFrom:
                secretKeyRef:
                  key: latest
                  name: agentdrive-voyage-api-key
            - name: COHERE_API_KEY
              valueFrom:
                secretKeyRef:
                  key: latest
                  name: agentdrive-cohere-api-key
            - name: ANTHROPIC_API_KEY
              valueFrom:
                secretKeyRef:
                  key: latest
                  name: agentdrive-anthropic-api-key
            - name: WORKOS_API_KEY
              valueFrom:
                secretKeyRef:
                  key: latest
                  name: agentdrive-workos-api-key
          startupProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
            failureThreshold: 3
```

GitHub Actions replaces the `image` tag with the actual commit SHA before deploying.

## CI/CD Pipeline

```
Push to main
     │
     ▼
┌─────────────────────────────────────┐
│  GitHub Actions: deploy.yml         │
│                                     │
│  1. Checkout code                   │
│  2. Auth to GCP (Workload Identity) │
│  3. Build Docker image              │
│  4. Push to Artifact Registry       │
│  5. Run Alembic migrations          │
│  6. Deploy to Cloud Run             │
│  7. Verify /health returns 200      │
└─────────────────────────────────────┘
```

### Authentication

Workload Identity Federation — GitHub Actions authenticates to GCP without a service account key. A GCP service account (`github-deployer`) gets bound to the GitHub repo via an OIDC provider.

### Migrations

Run from GitHub Actions runner using Cloud SQL Auth Proxy as a sidecar. Alembic connects via the proxy, runs `upgrade head`, then the new image deploys.

### Artifact Registry

Repository: `us-central1-docker.pkg.dev/agent-drive-491013/agentdrive`
Image: `api:<commit-sha>`

### Rollback

Cloud Run keeps previous revisions. Rollback via `gcloud run services update-traffic` to shift traffic back to a prior revision.

## DNS & SSL

1. Create Cloud Run domain mapping: `gcloud run domain-mappings create --service agentdrive-api --domain api.agentdrive.so --region us-central1`
2. Add CNAME record in Namecheap DNS panel: `api` → `ghs.googlehosted.com.`
3. Google provisions a managed SSL certificate automatically
4. Certificate propagation: 15–30 minutes after DNS is pointed

## Install Script Route

Add a route to the FastAPI app that serves `scripts/install.sh` as plain text:

```
GET https://api.agentdrive.so/install.sh
    → Response: text/plain, contents of install.sh
    → Usage: curl -fsSL https://api.agentdrive.so/install.sh | sh
```

Implementation: a single route in `main.py` that returns a `PlainTextResponse` with the script contents. The script is baked into the Docker image since it's in the repo.

## IAM & Service Accounts

| Service Account | Purpose | Roles |
|----------------|---------|-------|
| `agentdrive-api` | Cloud Run runtime | `roles/cloudsql.client`, `roles/secretmanager.secretAccessor`, `roles/storage.objectAdmin` |
| `github-deployer` | CI/CD deploys | `roles/run.admin`, `roles/artifactregistry.writer`, `roles/cloudsql.client`, `roles/iam.serviceAccountUser` |

## Estimated Cost

| Resource | Monthly Cost |
|----------|-------------|
| Cloud SQL `db-f1-micro` | ~$7–10 |
| Cloud Run (scales to zero) | ~$0–5 (usage-based) |
| Artifact Registry | ~$0.10/GB |
| Secret Manager | ~$0 (5 secrets, low access) |
| GCS | ~$0–2 (usage-based) |
| **Total** | **~$10–15/mo** |

## Out of Scope

- Staging environment (add later)
- Cloud Armor WAF
- Cloud SQL HA (regional)
- Monitoring/alerting dashboards
- CDN / Cloudflare in front of API
- Vanity domain for install script (`agentdrive.dev`)
