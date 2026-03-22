# API Key Management — Design Spec

**Issue:** #4
**Date:** 2026-03-22
**Status:** Approved

## Overview

Replace manual SQL-based API key creation with a self-service flow: users authenticate via WorkOS (device authorization flow), receive an `sk-ad-` API key, and the CLI stores it locally. API key auth switches from O(n) bcrypt scan to O(1) prefix-based lookup.

## User Flow

```
$ agentdrive login
  → opens browser → WorkOS AuthKit login
  → CLI polls backend with device code
  → backend verifies WorkOS token
  → backend finds or creates tenant (if auto-provisioning enabled)
  → backend generates sk-ad- API key
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

### Human Auth (CLI login)

1. CLI calls `POST /auth/device` → gets `device_code`, `user_code`, `verification_url`
2. CLI opens browser to verification URL
3. User authenticates via WorkOS AuthKit
4. CLI polls `POST /auth/token` with `device_code`
5. Backend verifies with WorkOS, resolves user
6. Backend finds tenant by `workos_user_id` or creates one (if `AUTO_PROVISION_TENANTS=true`)
7. Backend generates `sk-ad-` key, stores hash + prefix in `api_keys`
8. Returns raw key to CLI (shown once, never stored server-side)
9. CLI writes to `~/.agentdrive/credentials`

### Machine Auth (every API request)

1. Extract prefix from bearer token (8 chars after `sk-ad-`)
2. `SELECT * FROM api_keys WHERE key_prefix = ? AND revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now())`
3. bcrypt compare full key against `key_hash`
4. `UPDATE last_used = now()` (acceptable write-per-request for current scale; batch/sample later if needed)
5. Return associated tenant

**Legacy fallback:** Keys without `sk-ad-` prefix hit a fallback path that queries `key_prefix = 'legacy__'` and loops bcrypt comparisons. Removed once all tenants rotate.

## API Endpoints

### Auth (unauthenticated)

| Method | Path           | Description                              |
|--------|----------------|------------------------------------------|
| POST   | /auth/device   | Start device authorization flow          |
| POST   | /auth/token    | Poll for token (exchange device code)    |

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
│   ├── auth.py              ← NEW (device flow endpoints)
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
2. **Device authorization flow** — industry standard for CLI auth, works in SSH/headless
3. **O(1) prefix lookup** — 8-char plaintext prefix indexed for fast auth instead of O(n) bcrypt scan
4. **Auto-provisioning with flag** — seamless onboarding, gatekeeping when needed
5. **1 user = 1 tenant** — simple for now, org/team support added later with web dashboard
6. **Credentials file over env var mutation** — keeps MCP config clean, env var override for flexibility
7. **Legacy fallback** — existing keys keep working with placeholder prefix until rotated
