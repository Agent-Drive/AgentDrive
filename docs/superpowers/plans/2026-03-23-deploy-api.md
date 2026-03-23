# Deploy Agent Drive API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the Agent Drive FastAPI application to Cloud Run at `api.agentdrive.so` with Cloud SQL, Secret Manager, and GitHub Actions CI/CD.

**Architecture:** Cloud Run service connects to Cloud SQL (PostgreSQL 16 + pgvector) via Unix socket. Secrets injected from Secret Manager. GitHub Actions builds Docker image, runs Alembic migrations via Cloud SQL Proxy, and deploys on push to main.

**Tech Stack:** GCP Cloud Run, Cloud SQL, Secret Manager, Artifact Registry, Workload Identity Federation, GitHub Actions, Alembic, FastAPI

**Spec:** `docs/superpowers/specs/2026-03-23-deploy-api-design.md`

---

## File Structure

| Action | Path | Purpose |
|--------|------|---------|
| Create | `cloud-run/service.yaml` | Declarative Cloud Run service config |
| Create | `.github/workflows/deploy.yml` | CI/CD pipeline |
| Modify | `Dockerfile` | Add `COPY scripts/ scripts/` |
| Modify | `pyproject.toml` | Add `migrations` optional dep |
| Modify | `src/agentdrive/main.py` | Add `/install.sh` route |
| Create | `tests/test_install_route.py` | Test for install.sh route |
| Create | `.dockerignore` | Exclude .git, tests, docs from build context |

---

### Task 1: Add `/install.sh` route to FastAPI app

**Files:**
- Modify: `src/agentdrive/main.py`
- Create: `tests/test_install_route.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_install_route.py`:

```python
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from agentdrive.main import app


@pytest.mark.asyncio
async def test_install_sh_returns_script():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/install.sh")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "Installing Agent Drive MCP" in response.text


@pytest.mark.asyncio
async def test_install_sh_is_valid_shell():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/install.sh")

    assert response.text.startswith("#!/bin/sh")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_install_route.py -v`
Expected: FAIL (404 — route doesn't exist yet)

- [ ] **Step 3: Write minimal implementation**

Add to `src/agentdrive/main.py` inside `create_app()`, after the health endpoint:

```python
from pathlib import Path
from fastapi.responses import PlainTextResponse

# Inside create_app(), after the health endpoint:

    @app.get("/install.sh", response_class=PlainTextResponse)
    async def install_script():
        script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "install.sh"
        return PlainTextResponse(script_path.read_text())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_install_route.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/main.py tests/test_install_route.py
git commit -m "feat: add /install.sh route for curl | sh install"
```

---

### Task 2: Update Dockerfile and pyproject.toml

**Files:**
- Modify: `Dockerfile`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add `COPY scripts/ scripts/` to Dockerfile**

In `Dockerfile`, after `COPY alembic.ini .`, add:

```dockerfile
COPY scripts/ scripts/
```

- [ ] **Step 2: Add `migrations` optional dependency to pyproject.toml**

In `pyproject.toml`, after the `dev` optional dependencies block, add:

```toml
migrations = [
    "psycopg2-binary>=2.9.0",
]
```

- [ ] **Step 3: Create `.dockerignore`**

Create `.dockerignore`:

```
.git
tests/
docs/
*.md
.env*
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 4: Verify Docker build succeeds**

Run: `docker build -t agentdrive-api:test .`
Expected: Build completes successfully

- [ ] **Step 5: Commit**

```bash
git add Dockerfile pyproject.toml .dockerignore
git commit -m "chore: add scripts/ to Docker image, .dockerignore, and psycopg2-binary migration dep"
```

---

### Task 3: Create Cloud Run service.yaml

**Files:**
- Create: `cloud-run/service.yaml`

- [ ] **Step 1: Create `cloud-run/` directory and `service.yaml`**

Create `cloud-run/service.yaml`:

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
              memory: 2Gi
          env:
            - name: ENVIRONMENT
              value: production
            - name: GCS_BUCKET
              value: agentdrive-files
            - name: WORKOS_CLIENT_ID
              value: client_PLACEHOLDER
            - name: AUTO_PROVISION_TENANTS
              value: "false"
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
            timeoutSeconds: 5
            failureThreshold: 6
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            periodSeconds: 30
            timeoutSeconds: 5
            failureThreshold: 3
```

- [ ] **Step 2: Commit**

```bash
git add cloud-run/service.yaml
git commit -m "feat: add declarative Cloud Run service config"
```

---

### Task 4: Create GitHub Actions deploy workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

- [ ] **Step 1: Create workflow file**

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to Cloud Run

on:
  push:
    branches: [main]

env:
  PROJECT_ID: agent-drive-491013
  REGION: us-central1
  SERVICE: agentdrive-api
  REPOSITORY: agentdrive
  IMAGE: api

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Authenticate to Google Cloud
        id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.WIF_PROVIDER }}
          service_account: ${{ secrets.WIF_SERVICE_ACCOUNT }}

      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v2

      - name: Configure Docker for Artifact Registry
        run: gcloud auth configure-docker ${{ env.REGION }}-docker.pkg.dev --quiet

      - name: Build and push Docker image
        run: |
          IMAGE_TAG="${{ env.REGION }}-docker.pkg.dev/${{ env.PROJECT_ID }}/${{ env.REPOSITORY }}/${{ env.IMAGE }}:${{ github.sha }}"
          docker build -t "${IMAGE_TAG}" .
          docker push "${IMAGE_TAG}"

      - name: Run Alembic migrations
        run: |
          # Install Cloud SQL Proxy
          curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.3/cloud-sql-proxy.linux.amd64
          chmod +x cloud-sql-proxy

          # Start proxy in background
          ./cloud-sql-proxy ${{ env.PROJECT_ID }}:${{ env.REGION }}:agentdrive-db --port 5432 &
          PROXY_PID=$!
          sleep 3

          # Install dependencies and run migrations
          pip install --quiet uv
          uv pip install --system -e ".[migrations]"
          DATABASE_URL="${{ secrets.MIGRATION_DATABASE_URL }}" alembic upgrade head

          # Cleanup
          kill $PROXY_PID

      - name: Deploy to Cloud Run
        run: |
          IMAGE_TAG="${{ env.REGION }}-docker.pkg.dev/${{ env.PROJECT_ID }}/${{ env.REPOSITORY }}/${{ env.IMAGE }}:${{ github.sha }}"
          sed -i "s|image: .*|image: ${IMAGE_TAG}|" cloud-run/service.yaml
          gcloud run services replace cloud-run/service.yaml --region ${{ env.REGION }}

      - name: Verify deployment
        run: |
          SERVICE_URL=$(gcloud run services describe ${{ env.SERVICE }} --region ${{ env.REGION }} --format 'value(status.url)')
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${SERVICE_URL}/health")
          if [ "$STATUS" != "200" ]; then
            echo "Health check failed with status $STATUS"
            exit 1
          fi
          echo "Health check passed: ${SERVICE_URL}/health"
```

- [ ] **Step 2: Validate YAML syntax**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/deploy.yml'))"`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add GitHub Actions deploy workflow for Cloud Run"
```

---

### Task 5: Enable GCP APIs

**Prerequisites:** Must be done before any infrastructure provisioning.

- [ ] **Step 1: Enable required APIs**

```bash
gcloud services enable \
  sqladmin.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project=agent-drive-491013
```

Expected: All APIs enabled (may take 1-2 minutes)

- [ ] **Step 2: Verify APIs are enabled**

```bash
gcloud services list --enabled --project=agent-drive-491013 \
  --filter="name:(sqladmin OR run OR artifactregistry OR secretmanager)" \
  --format="table(name)"
```

Expected: All 4 APIs listed

---

### Task 6: Create Artifact Registry repository

- [ ] **Step 1: Create Docker repository**

```bash
gcloud artifacts repositories create agentdrive \
  --repository-format=docker \
  --location=us-central1 \
  --project=agent-drive-491013 \
  --description="Agent Drive Docker images"
```

Expected: Repository created

- [ ] **Step 2: Verify**

```bash
gcloud artifacts repositories describe agentdrive \
  --location=us-central1 \
  --project=agent-drive-491013
```

---

### Task 7: Create GCS bucket

- [ ] **Step 1: Create the file storage bucket**

```bash
gcloud storage buckets create gs://agentdrive-files \
  --location=us-central1 \
  --project=agent-drive-491013 \
  --uniform-bucket-level-access
```

- [ ] **Step 2: Verify**

```bash
gcloud storage buckets describe gs://agentdrive-files --project=agent-drive-491013
```

---

### Task 8: Create Cloud SQL instance and database (takes 3-5 minutes)

- [ ] **Step 1: Create PostgreSQL 16 instance**

```bash
gcloud sql instances create agentdrive-db \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region=us-central1 \
  --project=agent-drive-491013 \
  --assign-ip \
  --storage-size=10GB \
  --storage-type=SSD
```

Expected: Instance created (takes 3-5 minutes)

**Note:** Uses public IP but no authorized networks — access is only via Cloud SQL Auth Proxy (Cloud Run connector annotation + local proxy for migrations). This is simpler than configuring Private Services Access for VPC peering and equally secure since the proxy handles authentication.

- [ ] **Step 2: Set postgres user password**

```bash
gcloud sql users set-password postgres \
  --instance=agentdrive-db \
  --project=agent-drive-491013 \
  --password=GENERATE_A_STRONG_PASSWORD
```

- [ ] **Step 3: Create the application database**

```bash
gcloud sql databases create agentdrive \
  --instance=agentdrive-db \
  --project=agent-drive-491013
```

- [ ] **Step 4: Enable pgvector extension**

Connect via Cloud SQL Proxy or `gcloud sql connect`:

```bash
gcloud sql connect agentdrive-db --user=postgres --project=agent-drive-491013
```

Then run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

- [ ] **Step 5: Verify**

```bash
gcloud sql instances describe agentdrive-db \
  --project=agent-drive-491013 \
  --format="table(name,databaseVersion,settings.tier,region,state)"
```

---

### Task 9: Create service accounts and IAM bindings

- [ ] **Step 1: Create Cloud Run service account**

```bash
gcloud iam service-accounts create agentdrive-api \
  --display-name="Agent Drive API (Cloud Run)" \
  --project=agent-drive-491013
```

- [ ] **Step 2: Grant Cloud Run SA roles**

```bash
PROJECT=agent-drive-491013
SA=agentdrive-api@${PROJECT}.iam.gserviceaccount.com

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:${SA}" \
  --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:${SA}" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:${SA}" \
  --role="roles/storage.objectAdmin"
```

- [ ] **Step 3: Create GitHub deployer service account**

```bash
gcloud iam service-accounts create github-deployer \
  --display-name="GitHub Actions Deployer" \
  --project=agent-drive-491013
```

- [ ] **Step 4: Grant deployer SA roles**

```bash
PROJECT=agent-drive-491013
SA=github-deployer@${PROJECT}.iam.gserviceaccount.com

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:${SA}" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:${SA}" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:${SA}" \
  --role="roles/cloudsql.client"

gcloud iam service-accounts add-iam-policy-binding \
  agentdrive-api@${PROJECT}.iam.gserviceaccount.com \
  --member="serviceAccount:${SA}" \
  --role="roles/iam.serviceAccountUser" \
  --project=$PROJECT
```

- [ ] **Step 5: Set up Workload Identity Federation for GitHub Actions**

```bash
PROJECT=agent-drive-491013
PROJECT_NUMBER=$(gcloud projects describe $PROJECT --format="value(projectNumber)")

# Create workload identity pool
gcloud iam workload-identity-pools create github-pool \
  --location=global \
  --display-name="GitHub Actions Pool" \
  --project=$PROJECT

# Create OIDC provider
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global \
  --workload-identity-pool=github-pool \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --project=$PROJECT

# Bind GitHub repo to deployer SA
REPO="Agent-Drive/AgentDrive"
gcloud iam service-accounts add-iam-policy-binding \
  github-deployer@${PROJECT}.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${REPO}" \
  --project=$PROJECT
```

- [ ] **Step 6: Commit (nothing to commit — infrastructure only)**

Note: This task is GCP infrastructure provisioning, no code changes.

---

### Task 10: Create secrets in Secret Manager

- [ ] **Step 1: Create secrets**

```bash
PROJECT=agent-drive-491013

# DATABASE_URL for Cloud Run (Unix socket format)
echo -n "postgresql+asyncpg://postgres:YOUR_PASSWORD@/agentdrive?host=/cloudsql/agent-drive-491013:us-central1:agentdrive-db" | \
  gcloud secrets create agentdrive-database-url --data-file=- --project=$PROJECT

# API keys (replace with actual values)
echo -n "YOUR_VOYAGE_API_KEY" | \
  gcloud secrets create agentdrive-voyage-api-key --data-file=- --project=$PROJECT

echo -n "YOUR_COHERE_API_KEY" | \
  gcloud secrets create agentdrive-cohere-api-key --data-file=- --project=$PROJECT

echo -n "YOUR_ANTHROPIC_API_KEY" | \
  gcloud secrets create agentdrive-anthropic-api-key --data-file=- --project=$PROJECT

echo -n "YOUR_WORKOS_API_KEY" | \
  gcloud secrets create agentdrive-workos-api-key --data-file=- --project=$PROJECT
```

- [ ] **Step 2: Verify secrets exist**

```bash
gcloud secrets list --project=agent-drive-491013
```

Expected: 5 secrets listed

- [ ] **Step 3: Add `MIGRATION_DATABASE_URL` to GitHub repo secrets**

```bash
# TCP format for CI migrations via Cloud SQL Proxy
gh secret set MIGRATION_DATABASE_URL --body "postgresql://postgres:YOUR_PASSWORD@localhost:5432/agentdrive"
```

- [ ] **Step 4: Add Workload Identity Provider to GitHub repo secrets**

```bash
PROJECT_NUMBER=$(gcloud projects describe agent-drive-491013 --format="value(projectNumber)")
gh secret set WIF_PROVIDER --body "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
gh secret set WIF_SERVICE_ACCOUNT --body "github-deployer@agent-drive-491013.iam.gserviceaccount.com"
```

---

### Task 11: Run Alembic migrations against production

- [ ] **Step 1: Install Cloud SQL Proxy locally**

```bash
# macOS
curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.3/cloud-sql-proxy.darwin.amd64
chmod +x cloud-sql-proxy
```

- [ ] **Step 2: Start proxy and run migrations**

```bash
# Start proxy in background
./cloud-sql-proxy agent-drive-491013:us-central1:agentdrive-db --port 5432 &
PROXY_PID=$!
sleep 3

# Install psycopg2-binary
uv pip install psycopg2-binary

# Run migrations
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/agentdrive uv run alembic upgrade head

# Cleanup
kill $PROXY_PID
```

Expected: All 3 migrations applied (001_initial_schema, 002_chunk_aliases, 003_api_keys)

---

### Task 12: Initial deploy to Cloud Run

- [ ] **Step 1: Build and push Docker image manually (first deploy)**

```bash
PROJECT=agent-drive-491013
REGION=us-central1
IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT}/agentdrive/api:initial"

gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet
docker build -t "${IMAGE_TAG}" .
docker push "${IMAGE_TAG}"
```

- [ ] **Step 2: Update service.yaml image tag and deploy**

Note: `sed -i ''` is macOS syntax. On Linux use `sed -i` (no empty string).

```bash
sed -i '' "s|image: .*|image: ${IMAGE_TAG}|" cloud-run/service.yaml
gcloud run services replace cloud-run/service.yaml --region us-central1 --project agent-drive-491013
```

- [ ] **Step 3: Verify health endpoint**

```bash
SERVICE_URL=$(gcloud run services describe agentdrive-api --region us-central1 --project agent-drive-491013 --format 'value(status.url)')
curl -s "${SERVICE_URL}/health"
```

Expected: `{"status":"ok","environment":"production"}`

- [ ] **Step 4: Verify install script route**

```bash
curl -s "${SERVICE_URL}/install.sh" | head -5
```

Expected: First 5 lines of `scripts/install.sh`

- [ ] **Step 5: Revert service.yaml image tag to placeholder**

```bash
sed -i '' "s|image: .*|image: us-central1-docker.pkg.dev/agent-drive-491013/agentdrive/api:latest|" cloud-run/service.yaml
```

---

### Task 13: Configure custom domain

**Note:** This task requires manual action in the Namecheap DNS panel.

- [ ] **Step 1: Create Cloud Run domain mapping**

```bash
gcloud run domain-mappings create \
  --service agentdrive-api \
  --domain api.agentdrive.so \
  --region us-central1 \
  --project agent-drive-491013
```

- [ ] **Step 2: Add CNAME record in Namecheap (MANUAL)**

Log in to Namecheap → Domain List → `agentdrive.so` → Advanced DNS:
- Type: `CNAME Record`
- Host: `api`
- Value: `ghs.googlehosted.com.`
- TTL: Automatic

- [ ] **Step 3: Wait for SSL certificate provisioning (15-30 min)**

```bash
gcloud run domain-mappings describe \
  --domain api.agentdrive.so \
  --region us-central1 \
  --project agent-drive-491013
```

Check that `certificateStatus` shows `ACTIVE`.

- [ ] **Step 4: Verify custom domain**

```bash
curl -s https://api.agentdrive.so/health
```

Expected: `{"status":"ok","environment":"production"}`

---

### Task 14: Final commit and push

- [ ] **Step 1: Verify all code changes are committed**

```bash
git status
```

Expected: Clean working tree

- [ ] **Step 2: Push to trigger first automated deploy**

```bash
git push origin main
```

- [ ] **Step 3: Monitor GitHub Actions run**

```bash
gh run watch
```

Expected: All steps pass (build, migrate, deploy, health check)
