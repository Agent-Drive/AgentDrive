import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentdrive.models.base import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5433/agentdrive_test",
)


@pytest.fixture(autouse=True)
def mock_enrichment_and_embedding():
    """Prevent real API calls during tests."""
    async def _noop_embed(*args, **kwargs) -> int:
        return 0

    async def _noop_enrich(doc_text, groups):
        return groups

    async def _noop_aliases(groups):
        return []

    with patch("agentdrive.services.ingest.embed_file_chunks", side_effect=_noop_embed), \
         patch("agentdrive.services.ingest.embed_file_aliases", side_effect=_noop_embed), \
         patch("agentdrive.services.ingest.enrich_chunks", side_effect=_noop_enrich), \
         patch("agentdrive.services.ingest.generate_table_aliases", side_effect=_noop_aliases):
        yield


@pytest_asyncio.fixture
async def db_engine():
    """Create engine, drop+recreate tables for clean state each test."""
    from sqlalchemy import text as sa_text

    engine = create_async_engine(TEST_DATABASE_URL, echo=False, pool_size=5)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(sa_text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # pgvector halfvec columns are added via migration, not ORM metadata
        await conn.execute(sa_text(
            "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding halfvec(256)"
        ))
        await conn.execute(sa_text(
            "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_full halfvec(1024)"
        ))
        await conn.execute(sa_text(
            "CREATE TABLE IF NOT EXISTS chunk_aliases ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "chunk_id uuid REFERENCES chunks(id) ON DELETE CASCADE, "
            "file_id uuid REFERENCES files(id) ON DELETE CASCADE, "
            "content text NOT NULL, "
            "token_count integer NOT NULL, "
            "created_at timestamptz DEFAULT now())"
        ))
        await conn.execute(sa_text(
            "ALTER TABLE chunk_aliases ADD COLUMN IF NOT EXISTS embedding halfvec(256)"
        ))
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
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(db_engine):
    """Session factory tied to test engine."""
    return async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(db_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Session for direct DB operations in tests."""
    async with db_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_engine, db_session_factory) -> AsyncGenerator[AsyncClient, None]:
    """Test HTTP client with FastAPI app using test DB."""
    from agentdrive.db.session import get_session
    from agentdrive.main import create_app

    app = create_app()

    async def override_session():
        async with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
