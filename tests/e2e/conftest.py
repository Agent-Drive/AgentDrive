"""E2E test fixtures. NO autouse mocks — hits real external APIs.

Requires a running server: uv run uvicorn agentdrive.main:app --port 8080
"""

import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from agentdrive.config import settings
from agentdrive.services.auth import generate_api_key

SERVER_URL = "http://localhost:8080"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Direct DB session using the database from .env."""
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """HTTP client pointing at a running local server."""
    async with AsyncClient(base_url=SERVER_URL, timeout=30.0) as client:
        # Verify server is running
        resp = await client.get("/health")
        assert resp.status_code == 200, (
            f"Server not running at {SERVER_URL}. Start it with: "
            "uv run uvicorn agentdrive.main:app --port 8080"
        )
        yield client


@pytest_asyncio.fixture
async def api_key(db_session: AsyncSession) -> AsyncGenerator[str, None]:
    """Seed a test tenant + API key, yield raw key, clean up after."""
    tenant_id = str(uuid.uuid4())
    key_id = str(uuid.uuid4())
    raw_key, prefix, key_hash = generate_api_key()

    await db_session.execute(
        text("INSERT INTO tenants (id, name, created_at, updated_at) VALUES (:id, 'e2e-test', NOW(), NOW())"),
        {"id": tenant_id},
    )
    await db_session.execute(
        text(
            "INSERT INTO api_keys (id, tenant_id, name, key_hash, key_prefix, created_at, updated_at) "
            "VALUES (:id, :tid, 'e2e-test', :hash, :prefix, NOW(), NOW())"
        ),
        {"id": key_id, "tid": tenant_id, "hash": key_hash, "prefix": prefix},
    )
    await db_session.commit()

    yield raw_key

    # Cleanup: delete in dependency order
    await db_session.execute(
        text("DELETE FROM chunk_aliases WHERE chunk_id IN (SELECT id FROM chunks WHERE file_id IN (SELECT id FROM files WHERE tenant_id = :tid))"),
        {"tid": tenant_id},
    )
    await db_session.execute(
        text("DELETE FROM chunks WHERE file_id IN (SELECT id FROM files WHERE tenant_id = :tid)"),
        {"tid": tenant_id},
    )
    await db_session.execute(
        text("DELETE FROM parent_chunks WHERE file_id IN (SELECT id FROM files WHERE tenant_id = :tid)"),
        {"tid": tenant_id},
    )
    await db_session.execute(
        text("DELETE FROM file_batches WHERE file_id IN (SELECT id FROM files WHERE tenant_id = :tid)"),
        {"tid": tenant_id},
    )
    await db_session.execute(
        text("DELETE FROM files WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    )
    await db_session.execute(text("DELETE FROM api_keys WHERE tenant_id = :tid"), {"tid": tenant_id})
    await db_session.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": tenant_id})
    await db_session.commit()
