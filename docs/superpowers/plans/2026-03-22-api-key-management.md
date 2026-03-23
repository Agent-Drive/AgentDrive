# API Key Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace manual SQL-based API key creation with self-service WorkOS device auth + API key CRUD, switching auth from O(n) bcrypt scan to O(1) prefix lookup.

**Architecture:** New `api_keys` table with prefix-indexed lookup. CLI authenticates directly with WorkOS via native device flow (RFC 8628), then exchanges the WorkOS access token for an `sk-ad-` key via our backend's `POST /auth/exchange`. Existing `tenants.api_key_hash` migrated to `api_keys` with legacy fallback. CLI stores credentials at `~/.agentdrive/credentials`, MCP server reads from there.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, bcrypt, WorkOS Python SDK, Typer (CLI), httpx

**Spec:** `docs/superpowers/specs/2026-03-22-api-key-management-design.md`

---

## File Structure

```
src/agentdrive/
├── models/
│   ├── __init__.py              ← MODIFY (add ApiKey import)
│   ├── tenant.py                ← MODIFY (drop api_key_hash, add workos_user_id, add api_keys relationship)
│   └── api_key.py               ← CREATE (ApiKey model)
├── services/
│   └── auth.py                  ← MODIFY (add generate_api_key, prefix auth functions)
├── schemas/
│   └── api_keys.py              ← CREATE (request/response schemas)
├── routers/
│   ├── api_keys.py              ← CREATE (CRUD endpoints)
│   └── auth.py                  ← CREATE (token exchange endpoint)
├── dependencies.py              ← MODIFY (O(1) prefix auth + legacy fallback)
├── config.py                    ← MODIFY (add WorkOS + auto-provision settings)
├── main.py                      ← MODIFY (register new routers)
├── cli/
│   ├── __init__.py              ← CREATE
│   ├── credentials.py           ← CREATE (read/write ~/.agentdrive/credentials)
│   └── main.py                  ← CREATE (typer app: login/logout/status/keys)
└── mcp/
    └── server.py                ← MODIFY (credentials fallback + new tools)

alembic/versions/
└── 003_api_keys.py              ← CREATE (migration)

tests/
├── test_auth.py                 ← MODIFY (add prefix auth tests)
├── test_api_keys.py             ← CREATE (key CRUD endpoint tests)
├── test_auth_endpoints.py       ← CREATE (device flow endpoint tests)
├── test_credentials.py          ← CREATE (CLI credentials tests)
└── conftest.py                  ← MODIFY (add api_keys table setup + new fixtures)

pyproject.toml                   ← MODIFY (add deps + CLI entry point)
```

---

### Task 1: Add dependencies and CLI entry point

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add workos and typer dependencies**

In `pyproject.toml`, add to the `dependencies` list:

```toml
    "workos>=4.0.0",
    "typer>=0.15.0",
    "PyJWT>=2.8.0",
```

- [ ] **Step 2: Add CLI entry point**

In `pyproject.toml`, add after the `[tool.hatch.build.targets.wheel]` section:

```toml
[project.scripts]
agentdrive = "agentdrive.cli.main:app"
```

- [ ] **Step 3: Install updated dependencies**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv sync`
Expected: dependencies install successfully

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add workos and typer dependencies + CLI entry point"
```

---

### Task 2: ApiKey model + updated Tenant model

**Files:**
- Create: `src/agentdrive/models/api_key.py`
- Modify: `src/agentdrive/models/tenant.py`
- Modify: `src/agentdrive/models/__init__.py`

- [ ] **Step 1: Write test for ApiKey model**

Create `tests/test_models_api_key.py`:

```python
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant


@pytest.mark.asyncio
async def test_create_api_key(db_session: AsyncSession):
    tenant = Tenant(name="Test Tenant")
    db_session.add(tenant)
    await db_session.flush()

    api_key = ApiKey(
        tenant_id=tenant.id,
        key_prefix="abc12345",
        key_hash="$2b$12$fakehashvalue",
        name="production",
    )
    db_session.add(api_key)
    await db_session.flush()

    result = await db_session.execute(select(ApiKey).where(ApiKey.tenant_id == tenant.id))
    keys = result.scalars().all()
    assert len(keys) == 1
    assert keys[0].key_prefix == "abc12345"
    assert keys[0].name == "production"
    assert keys[0].revoked_at is None
    assert keys[0].expires_at is None


@pytest.mark.asyncio
async def test_tenant_has_api_keys_relationship(db_session: AsyncSession):
    tenant = Tenant(name="Test Tenant")
    db_session.add(tenant)
    await db_session.flush()

    key1 = ApiKey(tenant_id=tenant.id, key_prefix="key1pre1", key_hash="hash1", name="dev")
    key2 = ApiKey(tenant_id=tenant.id, key_prefix="key2pre2", key_hash="hash2", name="prod")
    db_session.add_all([key1, key2])
    await db_session.flush()

    await db_session.refresh(tenant, ["api_keys"])
    assert len(tenant.api_keys) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/test_models_api_key.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentdrive.models.api_key'`

- [ ] **Step 3: Create ApiKey model**

Create `src/agentdrive/models/api_key.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class ApiKey(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "api_keys"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    key_prefix: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tenant = relationship("Tenant", back_populates="api_keys")
```

- [ ] **Step 4: Update Tenant model**

Modify `src/agentdrive/models/tenant.py` — replace entire file:

```python
from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Tenant(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tenants"
    name: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    workos_user_id: Mapped[str | None] = mapped_column(Text, unique=True)
    settings: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    collections = relationship("Collection", back_populates="tenant")
    files = relationship("File", back_populates="tenant")
    api_keys = relationship("ApiKey", back_populates="tenant")
```

Note: `api_key_hash` stays for now — we need it until the migration runs. It gets dropped in the migration task.

- [ ] **Step 5: Update models/__init__.py**

Add to `src/agentdrive/models/__init__.py`:

```python
from agentdrive.models.api_key import ApiKey
```

And add `"ApiKey"` to the `__all__` list.

- [ ] **Step 6: Update conftest.py for api_keys table**

In `tests/conftest.py`, inside the `db_engine` fixture, after the `chunk_aliases` table creation block, add:

```python
        await conn.execute(sa_text(
            "CREATE TABLE IF NOT EXISTS api_keys ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "tenant_id uuid REFERENCES tenants(id), "
            "key_prefix text NOT NULL, "
            "key_hash text NOT NULL, "
            "name text, "
            "created_at timestamptz DEFAULT now(), "
            "expires_at timestamptz, "
            "revoked_at timestamptz, "
            "last_used timestamptz)"
        ))
        await conn.execute(sa_text(
            "CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix)"
        ))
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/test_models_api_key.py -v`
Expected: PASS (both tests)

- [ ] **Step 8: Commit**

```bash
git add src/agentdrive/models/api_key.py src/agentdrive/models/tenant.py src/agentdrive/models/__init__.py tests/test_models_api_key.py tests/conftest.py
git commit -m "feat: add ApiKey model and tenant relationship"
```

---

### Task 3: API key generation and prefix auth service

**Files:**
- Modify: `src/agentdrive/services/auth.py`
- Modify: `tests/test_auth.py`

- [ ] **Step 1: Write tests for new auth functions**

Append to `tests/test_auth.py`:

```python
from agentdrive.services.auth import generate_api_key, parse_key_prefix, verify_api_key, KEY_PREFIX


def test_generate_api_key_format():
    raw_key, prefix, hashed = generate_api_key()
    assert raw_key.startswith(KEY_PREFIX)
    assert len(prefix) == 8
    assert raw_key[len(KEY_PREFIX):len(KEY_PREFIX) + 8] == prefix
    assert hashed != raw_key


def test_generate_api_key_verifies():
    raw_key, prefix, hashed = generate_api_key()
    assert verify_api_key(raw_key, hashed) is True


def test_generate_api_key_unique():
    key1, _, _ = generate_api_key()
    key2, _, _ = generate_api_key()
    assert key1 != key2


def test_parse_key_prefix_valid():
    prefix = parse_key_prefix("sk-ad-abc12345restofthekey")
    assert prefix == "abc12345"


def test_parse_key_prefix_legacy():
    prefix = parse_key_prefix("some-old-key-format")
    assert prefix is None


def test_parse_key_prefix_too_short():
    prefix = parse_key_prefix("sk-ad-ab")
    assert prefix is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/test_auth.py -v`
Expected: FAIL — `ImportError: cannot import name 'generate_api_key'`

- [ ] **Step 3: Implement new auth functions**

Replace `src/agentdrive/services/auth.py` with:

```python
import secrets
import string

import bcrypt

KEY_PREFIX = "sk-ad-"
PREFIX_LENGTH = 8
KEY_RANDOM_LENGTH = 32

_ALPHABET = string.ascii_letters + string.digits


def hash_api_key(key: str) -> str:
    return bcrypt.hashpw(key.encode(), bcrypt.gensalt()).decode()


def verify_api_key(key: str, hashed: str) -> bool:
    return bcrypt.checkpw(key.encode(), hashed.encode())


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        (raw_key, prefix, key_hash) — raw_key shown once, prefix stored plaintext, hash stored.
    """
    random_part = "".join(secrets.choice(_ALPHABET) for _ in range(KEY_RANDOM_LENGTH))
    prefix = random_part[:PREFIX_LENGTH]
    raw_key = f"{KEY_PREFIX}{random_part}"
    key_hash = hash_api_key(raw_key)
    return raw_key, prefix, key_hash


def parse_key_prefix(key: str) -> str | None:
    """Extract the 8-char prefix from an sk-ad- key. Returns None for legacy keys."""
    if not key.startswith(KEY_PREFIX):
        return None
    remainder = key[len(KEY_PREFIX):]
    if len(remainder) < PREFIX_LENGTH:
        return None
    return remainder[:PREFIX_LENGTH]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/test_auth.py -v`
Expected: PASS (all 9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/services/auth.py tests/test_auth.py
git commit -m "feat: add API key generation with sk-ad- prefix format"
```

---

### Task 4: Pydantic schemas for API key endpoints

**Files:**
- Create: `src/agentdrive/schemas/api_keys.py`

- [ ] **Step 1: Create schemas**

Create `src/agentdrive/schemas/api_keys.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel


class ApiKeyCreate(BaseModel):
    name: str | None = None
    expires_at: datetime | None = None


class ApiKeyCreateResponse(BaseModel):
    """Returned only on creation — includes the raw key (shown once)."""

    id: uuid.UUID
    key: str
    key_prefix: str
    name: str | None
    created_at: datetime
    expires_at: datetime | None


class ApiKeyResponse(BaseModel):
    """Used for list — never includes the full key."""

    id: uuid.UUID
    key_prefix: str
    name: str | None
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used: datetime | None

    model_config = {"from_attributes": True}


class ApiKeyListResponse(BaseModel):
    api_keys: list[ApiKeyResponse]
    total: int
```

- [ ] **Step 2: Commit**

```bash
git add src/agentdrive/schemas/api_keys.py
git commit -m "feat: add Pydantic schemas for API key endpoints"
```

---

### Task 5: API key CRUD router

**Files:**
- Create: `src/agentdrive/routers/api_keys.py`
- Create: `tests/test_api_keys.py`
- Modify: `src/agentdrive/main.py`

- [ ] **Step 1: Write tests for key CRUD endpoints**

Create `tests/test_api_keys.py`:

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key

TEST_API_KEY = "sk-ad-testpre1restofthekeythatislongenough"


@pytest_asyncio.fixture
async def authed_client(client, db_session: AsyncSession):
    tenant = Tenant(name="Test Tenant", api_key_hash=hash_api_key(TEST_API_KEY))
    db_session.add(tenant)
    await db_session.commit()
    client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    return client


@pytest.mark.asyncio
async def test_create_api_key(authed_client):
    response = await authed_client.post("/v1/api-keys", json={"name": "ci-key"})
    assert response.status_code == 201
    data = response.json()
    assert data["key"].startswith("sk-ad-")
    assert data["name"] == "ci-key"
    assert data["key_prefix"] == data["key"][len("sk-ad-"):len("sk-ad-") + 8]
    assert "id" in data


@pytest.mark.asyncio
async def test_list_api_keys(authed_client):
    await authed_client.post("/v1/api-keys", json={"name": "key-1"})
    await authed_client.post("/v1/api-keys", json={"name": "key-2"})
    response = await authed_client.get("/v1/api-keys")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2
    for key in data["api_keys"]:
        assert "key" not in key  # never expose full key in list
        assert "key_prefix" in key


@pytest.mark.asyncio
async def test_revoke_api_key(authed_client):
    create_resp = await authed_client.post("/v1/api-keys", json={"name": "to-revoke"})
    key_id = create_resp.json()["id"]
    delete_resp = await authed_client.delete(f"/v1/api-keys/{key_id}")
    assert delete_resp.status_code == 204

    # verify key shows as revoked in list
    list_resp = await authed_client.get("/v1/api-keys")
    revoked = [k for k in list_resp.json()["api_keys"] if k["id"] == key_id]
    assert len(revoked) == 1
    assert revoked[0]["revoked_at"] is not None


@pytest.mark.asyncio
async def test_revoke_nonexistent_key(authed_client):
    response = await authed_client.delete("/v1/api-keys/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_key_requires_auth(client):
    response = await client.post("/v1/api-keys", json={"name": "nope"})
    assert response.status_code in (401, 403)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/test_api_keys.py -v`
Expected: FAIL — 404s because routes don't exist

- [ ] **Step 3: Create API keys router**

Create `src/agentdrive/routers/api_keys.py`:

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.db.session import get_session
from agentdrive.dependencies import get_current_tenant
from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant
from agentdrive.schemas.api_keys import (
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
)
from agentdrive.services.auth import generate_api_key

router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"])


@router.post("", status_code=201, response_model=ApiKeyCreateResponse)
async def create_api_key(
    body: ApiKeyCreate,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    raw_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(
        tenant_id=tenant.id,
        key_prefix=prefix,
        key_hash=key_hash,
        name=body.name,
        expires_at=body.expires_at,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    return ApiKeyCreateResponse(
        id=api_key.id,
        key=raw_key,
        key_prefix=prefix,
        name=api_key.name,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
    )


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys(
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ApiKey)
        .where(ApiKey.tenant_id == tenant.id)
        .order_by(ApiKey.created_at)
    )
    keys = result.scalars().all()
    return ApiKeyListResponse(
        api_keys=[ApiKeyResponse.model_validate(k) for k in keys],
        total=len(keys),
    )


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant.id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    api_key.revoked_at = datetime.now(timezone.utc)
    await session.commit()
```

- [ ] **Step 4: Register router in main.py**

In `src/agentdrive/main.py`, add import:

```python
from agentdrive.routers import api_keys
```

And add after the existing `include_router` calls:

```python
    app.include_router(api_keys.router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/test_api_keys.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/routers/api_keys.py src/agentdrive/main.py tests/test_api_keys.py
git commit -m "feat: add API key CRUD endpoints (create, list, revoke)"
```

---

### Task 6: O(1) prefix-based auth + legacy fallback

**Files:**
- Modify: `src/agentdrive/dependencies.py`
- Create: `tests/test_prefix_auth.py`

- [ ] **Step 1: Write tests for new auth dependency**

Create `tests/test_prefix_auth.py`:

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import generate_api_key, hash_api_key

# Test with a new-format key
NEW_FORMAT_KEY = None  # will be generated in fixture
LEGACY_KEY = "old-style-key-no-prefix"


@pytest_asyncio.fixture
async def tenant_with_new_key(db_session: AsyncSession):
    """Create a tenant with a new-format sk-ad- key in api_keys table."""
    tenant = Tenant(name="New Format Tenant", api_key_hash="unused")
    db_session.add(tenant)
    await db_session.flush()

    raw_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(
        tenant_id=tenant.id,
        key_prefix=prefix,
        key_hash=key_hash,
        name="test",
    )
    db_session.add(api_key)
    await db_session.flush()
    return tenant, raw_key


@pytest_asyncio.fixture
async def tenant_with_legacy_key(db_session: AsyncSession):
    """Create a tenant with a legacy key in api_keys table (prefix='legacy__')."""
    tenant = Tenant(name="Legacy Tenant", api_key_hash=hash_api_key(LEGACY_KEY))
    db_session.add(tenant)
    await db_session.flush()

    api_key = ApiKey(
        tenant_id=tenant.id,
        key_prefix="legacy__",
        key_hash=hash_api_key(LEGACY_KEY),
        name="migrated",
    )
    db_session.add(api_key)
    await db_session.flush()
    return tenant


@pytest.mark.asyncio
async def test_auth_with_new_format_key(client, tenant_with_new_key):
    tenant, raw_key = tenant_with_new_key
    response = await client.get(
        "/v1/collections",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_with_legacy_key(client, tenant_with_legacy_key):
    response = await client.get(
        "/v1/collections",
        headers={"Authorization": f"Bearer {LEGACY_KEY}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_with_revoked_key(client, db_session: AsyncSession, tenant_with_new_key):
    tenant, raw_key = tenant_with_new_key
    from datetime import datetime, timezone
    from sqlalchemy import update
    from agentdrive.models.api_key import ApiKey as AK

    await db_session.execute(
        update(AK).where(AK.tenant_id == tenant.id).values(revoked_at=datetime.now(timezone.utc))
    )
    await db_session.commit()

    response = await client.get(
        "/v1/collections",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_with_invalid_key(client):
    response = await client.get(
        "/v1/collections",
        headers={"Authorization": "Bearer sk-ad-totally-fake-key-abc123"},
    )
    assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/test_prefix_auth.py -v`
Expected: FAIL — new key test fails because `dependencies.py` still uses the old O(n) scan on `tenant.api_key_hash` (not the `api_keys` table)

- [ ] **Step 3: Rewrite dependencies.py with prefix auth**

Replace `src/agentdrive/dependencies.py`:

```python
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.db.session import get_session
from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import parse_key_prefix, verify_api_key

security = HTTPBearer()


async def get_current_tenant(
    credentials: HTTPAuthorizationCredentials = Security(security),
    session: AsyncSession = Depends(get_session),
) -> Tenant:
    api_key = credentials.credentials
    prefix = parse_key_prefix(api_key)

    if prefix is not None:
        # New-format key: O(1) prefix lookup
        result = await session.execute(
            select(ApiKey)
            .where(
                ApiKey.key_prefix == prefix,
                ApiKey.revoked_at.is_(None),
            )
            .filter(
                (ApiKey.expires_at.is_(None)) | (ApiKey.expires_at > datetime.now(timezone.utc))
            )
        )
        candidates = result.scalars().all()
        for candidate in candidates:
            if verify_api_key(api_key, candidate.key_hash):
                # Update last_used
                await session.execute(
                    update(ApiKey)
                    .where(ApiKey.id == candidate.id)
                    .values(last_used=datetime.now(timezone.utc))
                )
                await session.commit()
                # Load tenant
                tenant_result = await session.execute(
                    select(Tenant).where(Tenant.id == candidate.tenant_id)
                )
                tenant = tenant_result.scalar_one_or_none()
                if tenant:
                    return tenant
    else:
        # Legacy fallback: keys without sk-ad- prefix
        result = await session.execute(
            select(ApiKey).where(
                ApiKey.key_prefix == "legacy__",
                ApiKey.revoked_at.is_(None),
            )
        )
        legacy_keys = result.scalars().all()
        for candidate in legacy_keys:
            if verify_api_key(api_key, candidate.key_hash):
                await session.execute(
                    update(ApiKey)
                    .where(ApiKey.id == candidate.id)
                    .values(last_used=datetime.now(timezone.utc))
                )
                await session.commit()
                tenant_result = await session.execute(
                    select(Tenant).where(Tenant.id == candidate.tenant_id)
                )
                tenant = tenant_result.scalar_one_or_none()
                if tenant:
                    return tenant

    raise HTTPException(status_code=401, detail="Invalid API key")
```

- [ ] **Step 4: Run prefix auth tests**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/test_prefix_auth.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Fix existing tests that use the old auth path**

The existing tests in `tests/test_search_api.py` and `tests/test_api_keys.py` create tenants with `api_key_hash` but no `api_keys` rows. They need to also insert an `ApiKey` row.

Update the `authed_client` fixture in `tests/test_search_api.py`:

```python
from agentdrive.models.api_key import ApiKey
from agentdrive.services.auth import hash_api_key, parse_key_prefix

TEST_API_KEY = "sk-ad-testpre1searchkeyforunittesting"


@pytest_asyncio.fixture
async def authed_client(client, db_session):
    tenant = Tenant(name="Test", api_key_hash="unused")
    db_session.add(tenant)
    await db_session.flush()

    prefix = parse_key_prefix(TEST_API_KEY)
    api_key = ApiKey(
        tenant_id=tenant.id,
        key_prefix=prefix,
        key_hash=hash_api_key(TEST_API_KEY),
        name="test",
    )
    db_session.add(api_key)
    await db_session.commit()
    client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    return client
```

Apply the same pattern to the `authed_client` fixture in `tests/test_api_keys.py`:

```python
from agentdrive.models.api_key import ApiKey
from agentdrive.services.auth import hash_api_key, parse_key_prefix

TEST_API_KEY = "sk-ad-testpre1restofthekeythatislongenough"


@pytest_asyncio.fixture
async def authed_client(client, db_session: AsyncSession):
    tenant = Tenant(name="Test Tenant", api_key_hash="unused")
    db_session.add(tenant)
    await db_session.flush()

    prefix = parse_key_prefix(TEST_API_KEY)
    api_key = ApiKey(
        tenant_id=tenant.id,
        key_prefix=prefix,
        key_hash=hash_api_key(TEST_API_KEY),
        name="test",
    )
    db_session.add(api_key)
    await db_session.commit()
    client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    return client
```

- [ ] **Step 6: Run all tests**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/test_auth.py tests/test_prefix_auth.py tests/test_api_keys.py tests/test_search_api.py -v`
Expected: PASS (all tests)

- [ ] **Step 7: Commit**

```bash
git add src/agentdrive/dependencies.py tests/test_prefix_auth.py tests/test_search_api.py tests/test_api_keys.py
git commit -m "feat: O(1) prefix-based auth with legacy fallback"
```

---

### Task 7: Config + WorkOS token exchange endpoint

**Files:**
- Modify: `src/agentdrive/config.py`
- Create: `src/agentdrive/routers/auth.py`
- Create: `tests/test_auth_endpoints.py`
- Modify: `src/agentdrive/main.py`

The CLI handles the WorkOS device flow directly (CLI ↔ WorkOS). Our backend only has one endpoint: `POST /auth/exchange` — accepts a WorkOS access token, resolves the user, finds/creates a tenant, and returns an `sk-ad-` API key.

- [ ] **Step 1: Update config.py with WorkOS settings**

Add to the `Settings` class in `src/agentdrive/config.py`:

```python
    workos_api_key: str = ""
    workos_client_id: str = ""
    auto_provision_tenants: bool = True
```

- [ ] **Step 2: Write tests for token exchange endpoint**

Create `tests/test_auth_endpoints.py`:

```python
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant


@pytest.mark.asyncio
async def test_exchange_creates_tenant(client, db_session: AsyncSession):
    """POST /auth/exchange with valid token should create tenant + return API key."""
    mock_user = MagicMock()
    mock_user.id = "workos-user-123"
    mock_user.email = "test@example.com"
    mock_user.first_name = "Test"
    mock_user.last_name = "User"

    with patch("agentdrive.routers.auth.get_workos_user") as mock_get_user:
        mock_get_user.return_value = mock_user
        response = await client.post(
            "/auth/exchange",
            json={"access_token": "fake-workos-access-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["api_key"].startswith("sk-ad-")
    assert data["email"] == "test@example.com"
    assert "tenant_id" in data

    # Verify tenant was created in DB
    result = await db_session.execute(
        select(Tenant).where(Tenant.workos_user_id == "workos-user-123")
    )
    tenant = result.scalar_one()
    assert tenant.name == "Test User"


@pytest.mark.asyncio
async def test_exchange_existing_tenant(client, db_session: AsyncSession):
    """POST /auth/exchange for existing user should reuse tenant, create new key."""
    tenant = Tenant(
        name="Existing User",
        api_key_hash="unused",
        workos_user_id="workos-user-456",
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)

    mock_user = MagicMock()
    mock_user.id = "workos-user-456"
    mock_user.email = "existing@example.com"
    mock_user.first_name = "Existing"
    mock_user.last_name = "User"

    with patch("agentdrive.routers.auth.get_workos_user") as mock_get_user:
        mock_get_user.return_value = mock_user
        response = await client.post(
            "/auth/exchange",
            json={"access_token": "fake-workos-access-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == str(tenant.id)


@pytest.mark.asyncio
async def test_exchange_invalid_token(client):
    """POST /auth/exchange with invalid token should return 401."""
    with patch("agentdrive.routers.auth.get_workos_user") as mock_get_user:
        mock_get_user.return_value = None
        response = await client.post(
            "/auth/exchange",
            json={"access_token": "invalid-token"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_exchange_auto_provision_disabled(client, db_session: AsyncSession):
    """POST /auth/exchange with auto-provision off should reject new users."""
    mock_user = MagicMock()
    mock_user.id = "workos-user-new"
    mock_user.email = "new@example.com"
    mock_user.first_name = "New"
    mock_user.last_name = "User"

    with patch("agentdrive.routers.auth.get_workos_user") as mock_get_user, \
         patch("agentdrive.routers.auth.settings") as mock_settings:
        mock_get_user.return_value = mock_user
        mock_settings.auto_provision_tenants = False
        mock_settings.workos_api_key = "fake"
        mock_settings.workos_client_id = "fake"
        response = await client.post(
            "/auth/exchange",
            json={"access_token": "fake-workos-access-token"},
        )

    assert response.status_code == 403
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/test_auth_endpoints.py -v`
Expected: FAIL — routes don't exist

- [ ] **Step 4: Create auth router**

Create `src/agentdrive/routers/auth.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.config import settings
from agentdrive.db.session import get_session
from agentdrive.models.api_key import ApiKey
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import generate_api_key

workos_client = None
if settings.workos_api_key and settings.workos_client_id:
    from workos import WorkOSClient

    workos_client = WorkOSClient(
        api_key=settings.workos_api_key,
        client_id=settings.workos_client_id,
    )


class ExchangeRequest(BaseModel):
    access_token: str


class ExchangeResponse(BaseModel):
    api_key: str
    email: str
    tenant_id: str


router = APIRouter(prefix="/auth", tags=["auth"])


def get_workos_user(access_token: str):
    """Decode WorkOS JWT access token, verify it, and return user. Returns None if invalid."""
    if not workos_client:
        return None
    try:
        import jwt

        # Decode without verification first to get the user ID (sub claim).
        # In production, verify signature against WorkOS JWKS:
        #   https://<authkit-domain>/oauth2/jwks
        payload = jwt.decode(access_token, options={"verify_signature": False})
        user_id = payload.get("sub")
        if not user_id:
            return None
        user = workos_client.user_management.get_user(user_id=user_id)
        return user
    except Exception:
        return None


@router.post("/exchange", response_model=ExchangeResponse)
async def exchange_token(
    body: ExchangeRequest,
    session: AsyncSession = Depends(get_session),
):
    """Exchange a WorkOS access token for an Agent Drive sk-ad- API key."""
    user = get_workos_user(body.access_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired WorkOS token")

    # Find or create tenant
    result = await session.execute(
        select(Tenant).where(Tenant.workos_user_id == user.id)
    )
    tenant = result.scalar_one_or_none()

    if tenant is None:
        if not settings.auto_provision_tenants:
            raise HTTPException(
                status_code=403,
                detail="Auto-provisioning is disabled. Contact your admin.",
            )
        name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email
        tenant = Tenant(
            name=name,
            api_key_hash="unused",
            workos_user_id=user.id,
        )
        session.add(tenant)
        await session.flush()

    # Generate API key
    raw_key, prefix, key_hash = generate_api_key()
    api_key = ApiKey(
        tenant_id=tenant.id,
        key_prefix=prefix,
        key_hash=key_hash,
        name="cli-login",
    )
    session.add(api_key)
    await session.commit()

    return ExchangeResponse(
        api_key=raw_key,
        email=user.email,
        tenant_id=str(tenant.id),
    )
```

**Note:** The access token from WorkOS is a JWT. The `sub` claim contains the WorkOS user ID. We decode it, extract `sub`, then call `workos_client.user_management.get_user(user_id=...)` to get the full user object. In production, verify the JWT signature against `https://<authkit-domain>/oauth2/jwks` — the initial implementation skips signature verification for simplicity but this MUST be added before production deployment.

- [ ] **Step 5: Register auth router in main.py**

In `src/agentdrive/main.py`, add import:

```python
from agentdrive.routers import auth
```

And add to `create_app()`:

```python
    app.include_router(auth.router)
```

- [ ] **Step 6: Run tests**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/test_auth_endpoints.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 7: Commit**

```bash
git add src/agentdrive/config.py src/agentdrive/routers/auth.py src/agentdrive/main.py tests/test_auth_endpoints.py
git commit -m "feat: WorkOS token exchange endpoint (POST /auth/exchange)"
```

---

### Task 8: CLI (credentials + commands)

**Files:**
- Create: `src/agentdrive/cli/__init__.py`
- Create: `src/agentdrive/cli/credentials.py`
- Create: `src/agentdrive/cli/main.py`
- Create: `tests/test_credentials.py`

- [ ] **Step 1: Write tests for credentials module**

Create `tests/test_credentials.py`:

```python
import json
from pathlib import Path

import pytest

from agentdrive.cli.credentials import (
    load_credentials,
    save_credentials,
    delete_credentials,
    CREDENTIALS_DIR,
    CREDENTIALS_FILE,
)


@pytest.fixture
def tmp_creds(tmp_path, monkeypatch):
    """Redirect credentials to a temp directory."""
    creds_dir = tmp_path / ".agentdrive"
    creds_file = creds_dir / "credentials"
    monkeypatch.setattr("agentdrive.cli.credentials.CREDENTIALS_DIR", creds_dir)
    monkeypatch.setattr("agentdrive.cli.credentials.CREDENTIALS_FILE", creds_file)
    return creds_file


def test_save_and_load_credentials(tmp_creds):
    save_credentials(
        api_key="sk-ad-test1234restofkey",
        email="test@example.com",
        tenant_id="some-uuid",
    )
    assert tmp_creds.exists()
    # Check file permissions (owner read/write only)
    assert oct(tmp_creds.stat().st_mode)[-3:] == "600"

    creds = load_credentials()
    assert creds["api_key"] == "sk-ad-test1234restofkey"
    assert creds["email"] == "test@example.com"
    assert creds["tenant_id"] == "some-uuid"


def test_load_credentials_missing(tmp_creds):
    creds = load_credentials()
    assert creds is None


def test_delete_credentials(tmp_creds):
    save_credentials(api_key="sk-ad-x", email="x@x.com", tenant_id="x")
    assert tmp_creds.exists()
    delete_credentials()
    assert not tmp_creds.exists()


def test_delete_credentials_missing(tmp_creds):
    """Should not raise when file doesn't exist."""
    delete_credentials()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/test_credentials.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Create credentials module**

Create `src/agentdrive/cli/__init__.py` (empty file).

Create `src/agentdrive/cli/credentials.py`:

```python
import json
import os
from datetime import datetime, timezone
from pathlib import Path

CREDENTIALS_DIR = Path.home() / ".agentdrive"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials"


def save_credentials(api_key: str, email: str, tenant_id: str) -> None:
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "api_key": api_key,
        "email": email,
        "tenant_id": tenant_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    CREDENTIALS_FILE.write_text(json.dumps(data, indent=2))
    os.chmod(CREDENTIALS_FILE, 0o600)


def load_credentials() -> dict | None:
    if not CREDENTIALS_FILE.exists():
        return None
    return json.loads(CREDENTIALS_FILE.read_text())


def delete_credentials() -> None:
    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest tests/test_credentials.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Create CLI main module**

Create `src/agentdrive/cli/main.py`:

```python
import os
import time
import webbrowser

import httpx
import typer

from agentdrive.cli.credentials import delete_credentials, load_credentials, save_credentials

app = typer.Typer(name="agentdrive", help="Agent Drive CLI")

DEFAULT_API_URL = "http://localhost:8080"
# WorkOS AuthKit domain — set via env or configure per environment
WORKOS_AUTHKIT_DOMAIN = os.environ.get("WORKOS_AUTHKIT_DOMAIN", "")
WORKOS_CLIENT_ID = os.environ.get("WORKOS_CLIENT_ID", "")


def _get_api_url() -> str:
    return os.environ.get("AGENT_DRIVE_URL", DEFAULT_API_URL)


@app.command()
def login():
    """Authenticate with Agent Drive via browser login (WorkOS device flow)."""
    if not WORKOS_AUTHKIT_DOMAIN or not WORKOS_CLIENT_ID:
        typer.echo("Error: WORKOS_AUTHKIT_DOMAIN and WORKOS_CLIENT_ID must be set.", err=True)
        raise typer.Exit(1)

    authkit_base = f"https://{WORKOS_AUTHKIT_DOMAIN}"

    # Step 1: Request device authorization from WorkOS directly
    typer.echo("Starting login...")
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            f"{authkit_base}/authorize/device",
            data={"client_id": WORKOS_CLIENT_ID},
        )
        if resp.status_code != 200:
            typer.echo(f"Error starting device auth: {resp.text}", err=True)
            raise typer.Exit(1)
        data = resp.json()

    device_code = data["device_code"]
    user_code = data["user_code"]
    verification_uri = data.get("verification_uri_complete", data["verification_uri"])
    interval = data.get("interval", 5)

    typer.echo(f"\n  Your code: {user_code}")
    typer.echo(f"  Press Enter to open browser, or visit: {verification_uri}")
    input()
    webbrowser.open(verification_uri)

    # Step 2: Poll WorkOS token endpoint
    typer.echo("Waiting for authentication...")
    with httpx.Client(timeout=30) as client:
        for _ in range(60):  # 5 minutes max
            time.sleep(interval)
            resp = client.post(
                f"{authkit_base}/token",
                data={
                    "client_id": WORKOS_CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            )
            if resp.status_code == 200:
                token_data = resp.json()
                access_token = token_data["access_token"]

                # Step 3: Exchange WorkOS token for Agent Drive API key
                api_url = _get_api_url()
                exchange_resp = httpx.post(
                    f"{api_url}/auth/exchange",
                    json={"access_token": access_token},
                    timeout=30,
                )
                if exchange_resp.status_code != 200:
                    typer.echo(f"Error exchanging token: {exchange_resp.text}", err=True)
                    raise typer.Exit(1)

                result = exchange_resp.json()
                save_credentials(
                    api_key=result["api_key"],
                    email=result["email"],
                    tenant_id=result["tenant_id"],
                )
                typer.echo(f"\n  Logged in as {result['email']}")
                typer.echo("  API key stored in ~/.agentdrive/credentials")
                typer.echo("  Ready to use!")
                return

            error = resp.json().get("error", "")
            if error == "slow_down":
                interval += 5
            elif error in ("access_denied", "expired_token"):
                typer.echo(f"Login failed: {error}", err=True)
                raise typer.Exit(1)
            # "authorization_pending" — keep polling

    typer.echo("Login timed out. Please try again.", err=True)
    raise typer.Exit(1)


@app.command()
def logout():
    """Remove stored credentials."""
    delete_credentials()
    typer.echo("Logged out. Credentials removed.")


@app.command()
def status():
    """Show current authentication status."""
    creds = load_credentials()
    if not creds:
        typer.echo("Not logged in. Run 'agentdrive login' to authenticate.")
        raise typer.Exit(1)
    typer.echo(f"  Email:     {creds['email']}")
    typer.echo(f"  Tenant:    {creds['tenant_id']}")
    typer.echo(f"  Key:       {creds['api_key'][:14]}...")
    typer.echo(f"  Since:     {creds.get('created_at', 'unknown')}")


@app.command()
def keys():
    """List API keys for your tenant."""
    creds = load_credentials()
    if not creds:
        typer.echo("Not logged in. Run 'agentdrive login' first.", err=True)
        raise typer.Exit(1)

    api_url = _get_api_url()
    with httpx.Client(base_url=api_url, timeout=30) as client:
        resp = client.get(
            "/v1/api-keys",
            headers={"Authorization": f"Bearer {creds['api_key']}"},
        )
        if resp.status_code != 200:
            typer.echo(f"Error: {resp.text}", err=True)
            raise typer.Exit(1)

    data = resp.json()
    if data["total"] == 0:
        typer.echo("No API keys found.")
        return

    typer.echo(f"\n  {'PREFIX':<12} {'NAME':<20} {'CREATED':<22} {'LAST USED':<22} {'STATUS'}")
    typer.echo(f"  {'─' * 12} {'─' * 20} {'─' * 22} {'─' * 22} {'─' * 10}")
    for key in data["api_keys"]:
        name = key.get("name") or "(none)"
        created = key["created_at"][:19] if key["created_at"] else "—"
        last_used = key["last_used"][:19] if key.get("last_used") else "never"
        status = "revoked" if key.get("revoked_at") else "active"
        typer.echo(f"  {key['key_prefix']:<12} {name:<20} {created:<22} {last_used:<22} {status}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 6: Verify CLI loads**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run agentdrive --help`
Expected: Shows help with `login`, `logout`, `status`, `keys` commands

- [ ] **Step 7: Commit**

```bash
git add src/agentdrive/cli/ tests/test_credentials.py
git commit -m "feat: agentdrive CLI with login/logout/status/keys commands"
```

---

### Task 9: MCP server — credentials fallback + new tools

**Files:**
- Modify: `src/agentdrive/mcp/server.py`

- [ ] **Step 1: Update MCP server key resolution**

At the top of `src/agentdrive/mcp/server.py`, replace the key resolution (lines 9-10) with:

```python
import json
import os
from pathlib import Path

AGENT_DRIVE_URL = os.environ.get("AGENT_DRIVE_URL", "http://localhost:8080")


def _resolve_api_key() -> str:
    """Resolve API key: env var > credentials file."""
    key = os.environ.get("AGENT_DRIVE_API_KEY", "")
    if key:
        return key
    creds_file = Path.home() / ".agentdrive" / "credentials"
    if creds_file.exists():
        creds = json.loads(creds_file.read_text())
        return creds.get("api_key", "")
    return ""


AGENT_DRIVE_API_KEY = _resolve_api_key()
```

- [ ] **Step 2: Add new MCP tools to list_tools**

In the `list_tools()` function, add after the `get_chunk` tool:

```python
        Tool(name="create_api_key", description="Create a new API key for your tenant.",
             inputSchema={"type": "object", "properties": {
                 "name": {"type": "string", "description": "Name for the key (e.g. 'production', 'ci')"},
             }}),
        Tool(name="list_api_keys", description="List all API keys for your tenant.",
             inputSchema={"type": "object", "properties": {}}),
        Tool(name="revoke_api_key", description="Revoke an API key by ID.",
             inputSchema={"type": "object", "properties": {
                 "key_id": {"type": "string", "description": "UUID of the key to revoke"},
             }, "required": ["key_id"]}),
```

- [ ] **Step 3: Add tool handlers in call_tool**

In the `call_tool()` function, add before the final `return [TextContent(...)]`:

```python
        elif name == "create_api_key":
            body = {}
            if "name" in arguments:
                body["name"] = arguments["name"]
            response = await client.post("/v1/api-keys", json=body)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "list_api_keys":
            response = await client.get("/v1/api-keys")
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
        elif name == "revoke_api_key":
            response = await client.delete(f"/v1/api-keys/{arguments['key_id']}")
            if response.status_code == 204:
                return [TextContent(type="text", text="API key revoked successfully.")]
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]
```

- [ ] **Step 4: Commit**

```bash
git add src/agentdrive/mcp/server.py
git commit -m "feat: MCP server credentials fallback + key management tools"
```

---

### Task 10: Alembic migration

**Files:**
- Create: `alembic/versions/003_api_keys.py`

- [ ] **Step 1: Create migration**

Create `alembic/versions/003_api_keys.py`:

```python
"""Add api_keys table, workos_user_id, migrate existing keys

Revision ID: 003
Revises: 002
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Create api_keys table
    op.create_table(
        "api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("key_prefix", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_api_keys_prefix", "api_keys", ["key_prefix"])
    op.create_index("idx_api_keys_tenant", "api_keys", ["tenant_id"])

    # Step 2: Migrate existing tenant keys to api_keys table
    op.execute("""
        INSERT INTO api_keys (tenant_id, key_prefix, key_hash, name)
        SELECT id, 'legacy__', api_key_hash, 'migrated'
        FROM tenants
        WHERE api_key_hash IS NOT NULL AND api_key_hash != ''
    """)

    # Step 3: Add workos_user_id to tenants
    op.add_column("tenants", sa.Column("workos_user_id", sa.Text()))
    op.create_index(
        "idx_tenants_workos_user",
        "tenants",
        ["workos_user_id"],
        unique=True,
        postgresql_where=sa.text("workos_user_id IS NOT NULL"),
    )

    # Step 4: Drop api_key_hash from tenants
    op.drop_column("tenants", "api_key_hash")


def downgrade() -> None:
    op.add_column("tenants", sa.Column("api_key_hash", sa.Text(), nullable=True))

    # Restore keys from api_keys (best effort — only legacy keys have matching hashes)
    op.execute("""
        UPDATE tenants SET api_key_hash = ak.key_hash
        FROM api_keys ak
        WHERE ak.tenant_id = tenants.id AND ak.key_prefix = 'legacy__'
    """)

    op.drop_index("idx_tenants_workos_user", "tenants")
    op.drop_column("tenants", "workos_user_id")
    op.drop_index("idx_api_keys_tenant", "api_keys")
    op.drop_index("idx_api_keys_prefix", "api_keys")
    op.drop_table("api_keys")
```

- [ ] **Step 2: Verify migration syntax**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && python -c "import alembic.versions; print('ok')" 2>/dev/null; echo "Syntax check: import the migration module"` — or simply review the file for correctness.

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/003_api_keys.py
git commit -m "feat: add migration 003 — api_keys table + workos_user_id + data migration"
```

---

### Task 11: Drop api_key_hash from Tenant model (post-migration)

**Files:**
- Modify: `src/agentdrive/models/tenant.py`

After the migration is written (which drops the column from the DB), update the ORM model to match.

- [ ] **Step 1: Remove api_key_hash from Tenant model**

Update `src/agentdrive/models/tenant.py` — remove the `api_key_hash` line so it becomes:

```python
from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Tenant(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tenants"
    name: Mapped[str] = mapped_column(Text, nullable=False)
    workos_user_id: Mapped[str | None] = mapped_column(Text, unique=True)
    settings: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    collections = relationship("Collection", back_populates="tenant")
    files = relationship("File", back_populates="tenant")
    api_keys = relationship("ApiKey", back_populates="tenant")
```

- [ ] **Step 2: Update test fixtures that set api_key_hash**

In all test files that create `Tenant(api_key_hash=...)`, remove or change that field:

**`tests/conftest.py`**: In `db_engine`, the tenants table DDL is created via `Base.metadata.create_all`. Since `api_key_hash` is dropped from the model, the test DB will no longer have that column. No change needed to conftest.

**`tests/test_search_api.py`**: Change `Tenant(name="Test", api_key_hash="unused")` → `Tenant(name="Test")`

**`tests/test_api_keys.py`**: Change `Tenant(name="Test Tenant", api_key_hash="unused")` → `Tenant(name="Test Tenant")`

**`tests/test_prefix_auth.py`**: Change `Tenant(name="...", api_key_hash="unused")` and `Tenant(name="...", api_key_hash=hash_api_key(LEGACY_KEY))` → remove `api_key_hash` parameter from both.

**`tests/test_auth_endpoints.py`**: Change `Tenant(name="Existing User", api_key_hash="unused", ...)` → remove `api_key_hash`.

- [ ] **Step 3: Run all tests**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest -v`
Expected: PASS (all tests)

- [ ] **Step 4: Commit**

```bash
git add src/agentdrive/models/tenant.py tests/
git commit -m "refactor: drop api_key_hash from Tenant model (moved to api_keys table)"
```

---

### Task 12: Run full test suite and verify

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run pytest -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Verify CLI loads**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run agentdrive --help`
Expected: Shows all commands

- [ ] **Step 3: Verify no import errors**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && uv run python -c "from agentdrive.main import app; from agentdrive.cli.main import app as cli; print('OK')"`
Expected: "OK"

- [ ] **Step 4: Final commit (if any fixes needed)**

Only if fixes were required in previous steps.
