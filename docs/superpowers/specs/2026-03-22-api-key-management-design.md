# API Key Management — Design Spec

**Issue:** #4
**Date:** 2026-03-22
**Status:** Approved

## Overview

Replace manual SQL-based API key creation with a self-service flow: users authenticate via WorkOS (device authorization flow), receive an `sk-ad-` API key, and the CLI stores it locally. API key auth switches from O(n) bcrypt scan to O(1) prefix-based lookup.

## User Flow

```
$ agentdrive login
  → CLI calls WorkOS /authorize/device (native device flow, RFC 8628)
  → CLI displays user_code, opens browser to verification_uri
  → user authenticates via WorkOS AuthKit in browser
  → CLI polls WorkOS /token until access_token is returned
  → CLI calls our backend POST /auth/exchange with access_token
  → backend resolves WorkOS user, finds/creates tenant, generates sk-ad- key
  → CLI stores key in ~/.agentdrive/credentials
  → done
```

## Data Model

### tenants (modified)

- **Drop:** `api_key_hash` (migrated to `api_keys` table)
- **Add:** `workos_user_id text` (nullable, unique where not null)

### api_keys (new)

| Column      | Type         | Notes                                    |
|-------------|--------------|------------------------------------------|
| id          | uuid PK      | `DEFAULT gen_random_uuid()`              |
| tenant_id   | uuid FK      | → tenants(id)                            |
| key_prefix  | text NOT NULL | first 8 chars after `sk-ad-`, indexed    |
| key_hash    | text NOT NULL | bcrypt hash of full key                  |
| name        | text          | nullable, e.g. "production", "github-ci" |
| created_at  | timestamptz   | `DEFAULT now()`                          |
| expires_at  | timestamptz   | nullable                                 |
| revoked_at  | timestamptz   | nullable, set on revocation              |
| last_used   | timestamptz   | nullable, updated on each auth           |

**Index:** `idx_api_keys_prefix ON api_keys(key_prefix)`

**Prefix collisions:** 8 alphanumeric chars gives ~2.8 trillion combinations. Collisions are astronomically unlikely, but the auth flow handles it correctly — the query may return multiple rows, and bcrypt compare is run against each match (typically 1).

### Key format

```
sk-ad-rfy83kq1xT9mZpL4nB7wCvDjHgF2sA6e
│     │       │
│     │       └── random (secret part)
│     └── prefix (8 chars, stored plaintext for O(1) lookup)
└── identifies as Agent Drive key
```

## Auth Flows

### Human Auth (CLI login — WorkOS native device flow)

1. CLI calls WorkOS `POST /authorize/device` → gets `device_code`, `user_code`, `verification_uri`, `verification_uri_complete`, `interval`
2. CLI displays `user_code`, opens browser to `verification_uri_complete`
3. User authenticates via WorkOS AuthKit in browser, confirms code
4. CLI polls WorkOS `POST /token` with `device_code` at the specified `interval` (default 5s)
5. WorkOS returns `access_token` + `refresh_token` once user completes auth
6. CLI calls our backend `POST /auth/exchange` with the `access_token`
7. Backend decodes/verifies the WorkOS access token (JWT), extracts user ID
8. Backend finds tenant by `workos_user_id` or creates one (if `AUTO_PROVISION_TENANTS=true`)
9. Backend generates `sk-ad-` key, stores hash + prefix in `api_keys`
10. Returns raw key + email + tenant_id to CLI (key shown once, never stored server-side)
11. CLI writes to `~/.agentdrive/credentials`

**Note:** The device flow (steps 1-5) happens directly between the CLI and WorkOS — our backend is not involved. Our backend only participates at step 6 (exchanging the WorkOS token for an `sk-ad-` key).

**WorkOS Dashboard setup:** Register `http://localhost:8080` (dev) and production URL as allowed redirect URIs in the WorkOS Dashboard under **Redirects**.

### Machine Auth (every API request)

1. Extract prefix from bearer token (8 chars after `sk-ad-`)
2. `SELECT * FROM api_keys WHERE key_prefix = ? AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now())`
3. bcrypt compare full key against `key_hash`
4. `UPDATE last_used = now()` (acceptable write-per-request for current scale; batch/sample later if needed)
5. Return associated tenant

**Legacy fallback:** Keys without `sk-ad-` prefix hit a fallback path that queries `key_prefix = 'legacy__'` and loops bcrypt comparisons. Removed once all tenants rotate.

## API Endpoints

### Auth (unauthenticated)

| Method | Path            | Description                                                    |
|--------|-----------------|----------------------------------------------------------------|
| POST   | /auth/exchange  | Exchange WorkOS access token for `sk-ad-` API key              |

**Note:** The device flow endpoints (`/authorize/device`, `/token`) are provided by WorkOS directly — the CLI talks to WorkOS, not our backend. Our backend only has the `/auth/exchange` endpoint.

### Key Management (authenticated via API key)

| Method | Path               | Description                                    |
|--------|--------------------|------------------------------------------------|
| POST   | /v1/api-keys       | Generate new key (returns raw key once)        |
| GET    | /v1/api-keys       | List keys (prefix, name, dates — never full key)|
| DELETE | /v1/api-keys/{id}  | Revoke key (sets revoked_at)                   |

## CLI

### Commands

| Command             | Description                          |
|---------------------|--------------------------------------|
| `agentdrive login`  | Device auth flow, stores key locally |
| `agentdrive logout` | Deletes `~/.agentdrive/credentials`  |
| `agentdrive status` | Shows current user/tenant info       |
| `agentdrive keys`   | Lists API keys                       |

### Credentials file

**Path:** `~/.agentdrive/credentials`
**Permissions:** `0600` (owner read/write only)

```json
{
  "api_key": "sk-ad-rfy83kq1xT9mZpL4n...",
  "email": "rafey@example.com",
  "tenant_id": "550e8400-...",
  "created_at": "2026-03-22T..."
}
```

### MCP server key resolution

1. Check `AGENT_DRIVE_API_KEY` env var (matches existing MCP server convention)
2. If empty → read `~/.agentdrive/credentials`
3. If neither → error: "Run `agentdrive login` first"

Priority: env var > credentials file.

## MCP Tools (new)

| Tool             | Description                    |
|------------------|--------------------------------|
| create_api_key   | Calls `POST /v1/api-keys`     |
| list_api_keys    | Calls `GET /v1/api-keys`      |
| revoke_api_key   | Calls `DELETE /v1/api-keys/{id}` |

## Migration (003_api_keys.py)

1. **Create** `api_keys` table with prefix index
2. **Migrate** existing `tenants.api_key_hash` → `api_keys` rows with `key_prefix = 'legacy__'` and `name = 'migrated'`
3. **Add** `workos_user_id` column to `tenants` (nullable, unique where not null)
4. **Drop** `api_key_hash` from `tenants`

## Configuration

### New environment variables

| Variable                | Description                     | Default |
|-------------------------|---------------------------------|---------|
| `WORKOS_API_KEY`        | WorkOS API key                  | —       |
| `WORKOS_CLIENT_ID`      | WorkOS client ID                | —       |
| `AUTO_PROVISION_TENANTS`| Auto-create tenants on login    | `true`  |

### New dependencies

| Package        | Purpose                     |
|----------------|-----------------------------|
| workos-python  | WorkOS SDK for auth         |
| typer          | CLI framework (built on click, adds type hints) |

## File Changes

```
src/agentdrive/
├── routers/
│   ├── auth.py              ← NEW (token exchange endpoint)
│   └── api_keys.py          ← NEW (key CRUD endpoints)
├── models/
│   └── api_key.py           ← NEW (SQLAlchemy model)
├── services/
│   └── auth.py              ← MODIFIED (prefix lookup + legacy fallback)
├── cli/
│   ├── __init__.py          ← NEW
│   ├── main.py              ← NEW (click/typer entrypoint)
│   └── credentials.py       ← NEW (read/write ~/.agentdrive/)
├── dependencies.py          ← MODIFIED (new auth logic)
├── config.py                ← MODIFIED (new env vars)
└── mcp/
    └── server.py            ← MODIFIED (read credentials + new tools)

alembic/versions/
└── 003_api_keys.py          ← NEW migration

pyproject.toml                   ← MODIFIED (add [project.scripts] agentdrive entry point)
```

## Design Decisions

1. **WorkOS for human auth, API keys for machine auth** — clean separation of concerns
2. **WorkOS native device flow (RFC 8628)** — CLI talks directly to WorkOS for auth, our backend only exchanges the resulting token for an `sk-ad-` key. Simpler than a custom device flow — no in-memory state, no callback endpoint.
3. **O(1) prefix lookup** — 8-char plaintext prefix indexed for fast auth instead of O(n) bcrypt scan
4. **Auto-provisioning with flag** — seamless onboarding, gatekeeping when needed
5. **1 user = 1 tenant** — simple for now, org/team support added later with web dashboard
6. **Credentials file over env var mutation** — keeps MCP config clean, env var override for flexibility
7. **Legacy fallback** — existing keys keep working with placeholder prefix until rotated
8. **WorkOS API key management considered but deferred** — WorkOS has built-in API key management (org-scoped, with widget), but it requires WorkOS Organizations. Keeping our custom `api_keys` table for now — more control, no org dependency. Revisit when adding multi-user/org support.
