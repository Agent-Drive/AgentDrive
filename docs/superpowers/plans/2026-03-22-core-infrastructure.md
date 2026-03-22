# Agent Drive Core Infrastructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational FastAPI service with file upload, GCS storage, Postgres data model, API key auth, and basic REST endpoints — everything needed before chunking and retrieval.

**Architecture:** Single FastAPI app with async SQLAlchemy for Postgres, google-cloud-storage for GCS, and Pydantic settings for config. Alembic for migrations. Structured as a Python package with clear module boundaries.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), asyncpg, Alembic, google-cloud-storage, pgvector, pytest, httpx (test client), Docker

**Spec:** `docs/superpowers/specs/2026-03-22-agent-drive-design.md`

---

## File Structure

```
agentdrive/
├── pyproject.toml                    # Project config, dependencies
├── Dockerfile                        # Container image
├── .env.example                      # Environment variable template
├── alembic.ini                       # Alembic config
├── alembic/
│   ├── env.py                        # Migration environment
│   └── versions/                     # Migration files
│       └── 001_initial_schema.py
├── src/
│   └── agentdrive/
│       ├── __init__.py
│       ├── main.py                   # FastAPI app entrypoint
│       ├── config.py                 # Pydantic settings (env vars)
│       ├── dependencies.py           # FastAPI dependency injection
│       ├── models/
│       │   ├── __init__.py
│       │   ├── base.py               # SQLAlchemy base, common mixins
│       │   ├── tenant.py             # Tenant model
│       │   ├── collection.py         # Collection model
│       │   ├── file.py               # File model
│       │   ├── chunk.py              # Chunk + ParentChunk models
│       │   └── types.py              # Enums (FileStatus, ContentType)
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── files.py              # Pydantic request/response schemas
│       │   ├── collections.py
│       │   └── common.py             # Shared schemas (pagination, errors)
│       ├── routers/
│       │   ├── __init__.py
│       │   ├── files.py              # /v1/files endpoints
│       │   └── collections.py        # /v1/collections endpoints
│       ├── services/
│       │   ├── __init__.py
│       │   ├── storage.py            # GCS file storage
│       │   ├── auth.py               # API key verification
│       │   └── file_type.py          # MIME/extension type detection
│       └── db/
│           ├── __init__.py
│           └── session.py            # Async engine + session factory
└── tests/
    ├── conftest.py                   # Shared fixtures (test DB, client)
    ├── test_config.py
    ├── test_auth.py
    ├── test_files.py
    ├── test_collections.py
    ├── test_storage.py
    └── test_file_type.py
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/agentdrive/__init__.py`
- Create: `src/agentdrive/config.py`
- Create: `src/agentdrive/main.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Create pyproject.toml with dependencies**

```toml
[project]
name = "agentdrive"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "pgvector>=0.3.0",
    "google-cloud-storage>=2.18.0",
    "pydantic-settings>=2.6.0",
    "python-multipart>=0.0.17",
    "bcrypt>=4.2.0",
    "httpx>=0.28.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.28.0",
    "testcontainers[postgres]>=4.8.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agentdrive"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create .env.example**

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/agentdrive

# GCS
GCS_BUCKET=agentdrive-files
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# Auth
API_KEY_HASH_ROUNDS=12

# Voyage AI
VOYAGE_API_KEY=your-key-here

# Cohere
COHERE_API_KEY=your-key-here

# Environment
ENVIRONMENT=development
```

- [ ] **Step 3: Create config.py with Pydantic settings**

```python
# src/agentdrive/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/agentdrive"
    gcs_bucket: str = "agentdrive-files"
    voyage_api_key: str = ""
    cohere_api_key: str = ""
    environment: str = "development"
    max_upload_bytes: int = 32 * 1024 * 1024  # 32MB

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 4: Write failing test for config**

```python
# tests/test_config.py
import os

def test_settings_loads_defaults():
    from agentdrive.config import Settings
    s = Settings(database_url="postgresql+asyncpg://test:test@localhost/test")
    assert s.max_upload_bytes == 32 * 1024 * 1024
    assert s.environment == "development"

def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://custom:custom@db/mydb")
    monkeypatch.setenv("GCS_BUCKET", "my-bucket")
    from agentdrive.config import Settings
    s = Settings()
    assert s.gcs_bucket == "my-bucket"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && pip install -e ".[dev]" && pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Create main.py with FastAPI app**

```python
# src/agentdrive/main.py
from fastapi import FastAPI

from agentdrive.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agent Drive",
        version="0.1.0",
        description="Agent-native file intelligence layer",
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
```

- [ ] **Step 7: Create __init__.py**

```python
# src/agentdrive/__init__.py
```

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .env.example src/ tests/test_config.py
git commit -m "feat: project scaffolding with config and FastAPI app"
```

---

### Task 2: Database Connection + Models

**Files:**
- Create: `src/agentdrive/db/__init__.py`
- Create: `src/agentdrive/db/session.py`
- Create: `src/agentdrive/models/__init__.py`
- Create: `src/agentdrive/models/base.py`
- Create: `src/agentdrive/models/types.py`
- Create: `src/agentdrive/models/tenant.py`
- Create: `src/agentdrive/models/collection.py`
- Create: `src/agentdrive/models/file.py`
- Create: `src/agentdrive/models/chunk.py`
- Test: `tests/conftest.py`

- [ ] **Step 1: Create db/session.py**

```python
# src/agentdrive/db/session.py
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentdrive.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
```

```python
# src/agentdrive/db/__init__.py
```

- [ ] **Step 2: Create model types**

```python
# src/agentdrive/models/types.py
import enum


class FileStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ContentType(str, enum.Enum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    CODE = "code"
    JSON = "json"
    YAML = "yaml"
    CSV = "csv"
    XLSX = "xlsx"
    NOTEBOOK = "notebook"
    IMAGE = "image"
    TEXT = "text"
```

- [ ] **Step 3: Create base model**

```python
# src/agentdrive/models/base.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
```

- [ ] **Step 4: Create tenant model**

```python
# src/agentdrive/models/tenant.py
from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Tenant(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    collections = relationship("Collection", back_populates="tenant")
    files = relationship("File", back_populates="tenant")
```

- [ ] **Step 5: Create collection model**

```python
# src/agentdrive/models/collection.py
import uuid

from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Collection(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    tenant = relationship("Tenant", back_populates="collections")
    files = relationship("File", back_populates="collection")
```

- [ ] **Step 6: Create file model**

```python
# src/agentdrive/models/file.py
import uuid

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey
from agentdrive.models.types import ContentType, FileStatus


class File(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "files"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collections.id")
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    gcs_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=FileStatus.PENDING)
    metadata: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    tenant = relationship("Tenant", back_populates="files")
    collection = relationship("Collection", back_populates="files")
    chunks = relationship("Chunk", back_populates="file", cascade="all, delete-orphan")
    parent_chunks = relationship("ParentChunk", back_populates="file", cascade="all, delete-orphan")
```

- [ ] **Step 7: Create chunk models**

```python
# src/agentdrive/models/chunk.py
import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class ParentChunk(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "parent_chunks"

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    file = relationship("File", back_populates="parent_chunks")
    chunks = relationship("Chunk", back_populates="parent_chunk")


class Chunk(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "chunks"

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parent_chunks.id")
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context_prefix: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    # embedding columns added via Alembic migration (pgvector types)
    metadata: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    file = relationship("File", back_populates="chunks")
    parent_chunk = relationship("ParentChunk", back_populates="chunks")
```

- [ ] **Step 8: Create models __init__.py**

```python
# src/agentdrive/models/__init__.py
from agentdrive.models.base import Base
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.collection import Collection
from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import ContentType, FileStatus

__all__ = [
    "Base",
    "Chunk",
    "Collection",
    "ContentType",
    "File",
    "FileStatus",
    "ParentChunk",
    "Tenant",
]
```

- [ ] **Step 9: Create test conftest with test DB fixture**

```python
# tests/conftest.py
import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentdrive.models.base import Base


TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/agentdrive_test"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(test_engine, db_session) -> AsyncGenerator[AsyncClient, None]:
    from agentdrive.db.session import get_session
    from agentdrive.main import create_app

    app = create_app()

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

- [ ] **Step 10: Commit**

```bash
git add src/agentdrive/db/ src/agentdrive/models/ tests/conftest.py
git commit -m "feat: database session and SQLAlchemy models"
```

---

### Task 3: Alembic Migrations

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/001_initial_schema.py`

- [ ] **Step 1: Initialize Alembic**

Run: `cd /Users/rafey/Development/Rafey/AgentDrive && alembic init alembic`

- [ ] **Step 2: Configure alembic.ini**

Edit `alembic.ini` — set `sqlalchemy.url` to empty (we'll use env.py):

```ini
# alembic.ini
[alembic]
script_location = alembic
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 3: Configure alembic/env.py**

```python
# alembic/env.py
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from agentdrive.config import settings
from agentdrive.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Convert async URL to sync for Alembic
sync_url = settings.database_url.replace("+asyncpg", "")


def run_migrations_online() -> None:
    connectable = create_engine(sync_url)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
```

- [ ] **Step 4: Create initial migration**

```python
# alembic/versions/001_initial_schema.py
"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("api_key_hash", sa.Text(), nullable=False),
        sa.Column("settings", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "collections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name"),
    )

    op.create_table(
        "files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("collection_id", UUID(as_uuid=True), sa.ForeignKey("collections.id")),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("gcs_path", sa.Text(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "parent_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("file_id", UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("file_id", UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_chunk_id", UUID(as_uuid=True), sa.ForeignKey("parent_chunks.id")),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("context_prefix", sa.Text(), nullable=False, server_default=""),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Vector columns (pgvector halfvec)
    op.execute("ALTER TABLE chunks ADD COLUMN embedding halfvec(256)")
    op.execute("ALTER TABLE chunks ADD COLUMN embedding_full halfvec(1024)")

    # HNSW indexes — separate for docs and code (different embedding spaces)
    op.execute("""
        CREATE INDEX idx_chunks_embedding_docs ON chunks
        USING hnsw (embedding halfvec_cosine_ops)
        WITH (m = 16, ef_construction = 128)
        WHERE content_type != 'code'
    """)
    op.execute("""
        CREATE INDEX idx_chunks_embedding_code ON chunks
        USING hnsw (embedding halfvec_cosine_ops)
        WITH (m = 16, ef_construction = 128)
        WHERE content_type = 'code'
    """)

    # Full-text search index
    op.execute("""
        CREATE INDEX idx_chunks_content_fts ON chunks
        USING gin (to_tsvector('english', content))
    """)

    # Foreign key indexes
    op.create_index("idx_files_tenant", "files", ["tenant_id"])
    op.create_index("idx_files_collection", "files", ["collection_id"])
    op.create_index("idx_collections_tenant", "collections", ["tenant_id"])
    op.create_index("idx_chunks_file", "chunks", ["file_id"])


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("parent_chunks")
    op.drop_table("files")
    op.drop_table("collections")
    op.drop_table("tenants")
```

- [ ] **Step 5: Run migration against test DB**

Run: `DATABASE_URL=postgresql://postgres:postgres@localhost:5432/agentdrive_test alembic upgrade head`
Expected: Tables created successfully

- [ ] **Step 6: Commit**

```bash
git add alembic.ini alembic/
git commit -m "feat: Alembic migrations with initial schema"
```

---

### Task 4: API Key Authentication

**Files:**
- Create: `src/agentdrive/services/__init__.py`
- Create: `src/agentdrive/services/auth.py`
- Create: `src/agentdrive/dependencies.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write failing tests for auth**

```python
# tests/test_auth.py
import bcrypt
import pytest

from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key, verify_api_key


def test_hash_api_key():
    key = "sk-test-key-12345"
    hashed = hash_api_key(key)
    assert hashed != key
    assert bcrypt.checkpw(key.encode(), hashed.encode())


def test_verify_api_key_valid():
    key = "sk-test-key-12345"
    hashed = hash_api_key(key)
    assert verify_api_key(key, hashed) is True


def test_verify_api_key_invalid():
    hashed = hash_api_key("sk-real-key")
    assert verify_api_key("sk-wrong-key", hashed) is False


@pytest.mark.asyncio
async def test_auth_dependency_rejects_missing_key(client):
    response = await client.get("/v1/files")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_dependency_rejects_invalid_key(client):
    response = await client.get("/v1/files", headers={"Authorization": "Bearer sk-invalid"})
    assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL (services.auth not found)

- [ ] **Step 3: Implement auth service**

```python
# src/agentdrive/services/__init__.py
```

```python
# src/agentdrive/services/auth.py
import bcrypt


def hash_api_key(key: str) -> str:
    return bcrypt.hashpw(key.encode(), bcrypt.gensalt()).decode()


def verify_api_key(key: str, hashed: str) -> bool:
    return bcrypt.checkpw(key.encode(), hashed.encode())
```

- [ ] **Step 4: Implement auth dependency**

```python
# src/agentdrive/dependencies.py
import uuid

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.db.session import get_session
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import verify_api_key

security = HTTPBearer()


async def get_current_tenant(
    credentials: HTTPAuthorizationCredentials = Security(security),
    session: AsyncSession = Depends(get_session),
) -> Tenant:
    api_key = credentials.credentials
    result = await session.execute(select(Tenant))
    tenants = result.scalars().all()

    for tenant in tenants:
        if verify_api_key(api_key, tenant.api_key_hash):
            return tenant

    raise HTTPException(status_code=401, detail="Invalid API key")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS (at least the unit tests; integration tests need routers wired)

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/services/ src/agentdrive/dependencies.py tests/test_auth.py
git commit -m "feat: API key authentication with bcrypt"
```

---

### Task 5: File Type Detection

**Files:**
- Create: `src/agentdrive/services/file_type.py`
- Test: `tests/test_file_type.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_file_type.py
from agentdrive.services.file_type import detect_content_type


def test_detect_pdf():
    assert detect_content_type("report.pdf", "application/pdf") == "pdf"

def test_detect_markdown():
    assert detect_content_type("README.md", "text/markdown") == "markdown"

def test_detect_python():
    assert detect_content_type("main.py", "text/x-python") == "code"

def test_detect_typescript():
    assert detect_content_type("index.ts", "application/typescript") == "code"

def test_detect_json():
    assert detect_content_type("config.json", "application/json") == "json"

def test_detect_yaml():
    assert detect_content_type("config.yaml", "text/yaml") == "yaml"

def test_detect_csv():
    assert detect_content_type("data.csv", "text/csv") == "csv"

def test_detect_xlsx():
    assert detect_content_type("data.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") == "xlsx"

def test_detect_notebook():
    assert detect_content_type("analysis.ipynb", "application/json") == "notebook"

def test_detect_image_png():
    assert detect_content_type("diagram.png", "image/png") == "image"

def test_detect_plain_text_fallback():
    assert detect_content_type("notes.txt", "text/plain") == "text"

def test_detect_unknown_falls_back_to_text():
    assert detect_content_type("mystery.xyz", "application/octet-stream") == "text"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_file_type.py -v`
Expected: FAIL

- [ ] **Step 3: Implement file type detection**

```python
# src/agentdrive/services/file_type.py
from pathlib import Path

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
    ".rb", ".c", ".cpp", ".h", ".hpp", ".swift", ".kt", ".scala",
    ".sh", ".bash", ".zsh", ".r", ".m", ".cs", ".php", ".lua",
    ".zig", ".nim", ".ex", ".exs", ".clj", ".hs", ".ml", ".vue",
    ".svelte",
}

EXTENSION_MAP = {
    ".pdf": "pdf",
    ".md": "markdown",
    ".mdx": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "json",  # treat TOML same as structured data
    ".csv": "csv",
    ".xlsx": "xlsx",
    ".xls": "xlsx",
    ".ipynb": "notebook",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".svg": "image",
    ".webp": "image",
    ".txt": "text",
    ".log": "text",
    ".rst": "text",
}


def detect_content_type(filename: str, mime_type: str | None = None) -> str:
    ext = Path(filename).suffix.lower()

    # Notebooks: .ipynb has .json mime but is really a notebook
    if ext == ".ipynb":
        return "notebook"

    # Code files by extension
    if ext in CODE_EXTENSIONS:
        return "code"

    # Known extensions
    if ext in EXTENSION_MAP:
        return EXTENSION_MAP[ext]

    # Fallback to MIME type
    if mime_type:
        if "pdf" in mime_type:
            return "pdf"
        if "image" in mime_type:
            return "image"
        if "json" in mime_type:
            return "json"
        if "yaml" in mime_type or "yml" in mime_type:
            return "yaml"

    return "text"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_file_type.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/services/file_type.py tests/test_file_type.py
git commit -m "feat: file type detection from extension and MIME type"
```

---

### Task 6: GCS Storage Service

**Files:**
- Create: `src/agentdrive/services/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing tests (with mock GCS)**

```python
# tests/test_storage.py
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentdrive.services.storage import StorageService


@pytest.fixture
def storage():
    with patch("agentdrive.services.storage.storage_client") as mock_client:
        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket
        svc = StorageService()
        svc._bucket = mock_bucket
        yield svc, mock_bucket


def test_generate_gcs_path(storage):
    svc, _ = storage
    tenant_id = uuid.uuid4()
    file_id = uuid.uuid4()
    path = svc.generate_path(tenant_id, file_id, "report.pdf")
    assert str(tenant_id) in path
    assert str(file_id) in path
    assert path.endswith("report.pdf")


def test_upload_file(storage):
    svc, mock_bucket = storage
    tenant_id = uuid.uuid4()
    file_id = uuid.uuid4()
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    path = svc.upload(tenant_id, file_id, "report.pdf", b"file content", "application/pdf")

    mock_blob.upload_from_string.assert_called_once_with(b"file content", content_type="application/pdf")
    assert "report.pdf" in path


def test_download_file(storage):
    svc, mock_bucket = storage
    mock_blob = MagicMock()
    mock_blob.download_as_bytes.return_value = b"file content"
    mock_bucket.blob.return_value = mock_blob

    data = svc.download("tenants/abc/files/def/report.pdf")
    assert data == b"file content"


def test_delete_file(storage):
    svc, mock_bucket = storage
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    svc.delete("tenants/abc/files/def/report.pdf")
    mock_blob.delete.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL

- [ ] **Step 3: Implement storage service**

```python
# src/agentdrive/services/storage.py
import uuid

from google.cloud import storage as gcs

from agentdrive.config import settings

storage_client = gcs.Client()


class StorageService:
    def __init__(self) -> None:
        self._bucket = storage_client.bucket(settings.gcs_bucket)

    def generate_path(self, tenant_id: uuid.UUID, file_id: uuid.UUID, filename: str) -> str:
        return f"tenants/{tenant_id}/files/{file_id}/{filename}"

    def upload(
        self,
        tenant_id: uuid.UUID,
        file_id: uuid.UUID,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> str:
        path = self.generate_path(tenant_id, file_id, filename)
        blob = self._bucket.blob(path)
        blob.upload_from_string(data, content_type=content_type)
        return path

    def download(self, gcs_path: str) -> bytes:
        blob = self._bucket.blob(gcs_path)
        return blob.download_as_bytes()

    def delete(self, gcs_path: str) -> None:
        blob = self._bucket.blob(gcs_path)
        blob.delete()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/services/storage.py tests/test_storage.py
git commit -m "feat: GCS storage service for file upload/download"
```

---

### Task 7: Pydantic Schemas

**Files:**
- Create: `src/agentdrive/schemas/__init__.py`
- Create: `src/agentdrive/schemas/common.py`
- Create: `src/agentdrive/schemas/files.py`
- Create: `src/agentdrive/schemas/collections.py`

- [ ] **Step 1: Create schemas**

```python
# src/agentdrive/schemas/__init__.py
```

```python
# src/agentdrive/schemas/common.py
import uuid
from datetime import datetime

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str


class PaginationParams(BaseModel):
    offset: int = 0
    limit: int = 50
```

```python
# src/agentdrive/schemas/files.py
import uuid
from datetime import datetime

from pydantic import BaseModel


class FileUploadResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    status: str

    model_config = {"from_attributes": True}


class FileDetailResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    file_size: int
    status: str
    collection_id: uuid.UUID | None
    metadata: dict
    created_at: datetime
    chunk_count: int | None = None

    model_config = {"from_attributes": True}


class FileListResponse(BaseModel):
    files: list[FileDetailResponse]
    total: int
```

```python
# src/agentdrive/schemas/collections.py
import uuid
from datetime import datetime

from pydantic import BaseModel


class CollectionCreate(BaseModel):
    name: str
    description: str | None = None


class CollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    file_count: int | None = None

    model_config = {"from_attributes": True}


class CollectionListResponse(BaseModel):
    collections: list[CollectionResponse]
    total: int
```

- [ ] **Step 2: Commit**

```bash
git add src/agentdrive/schemas/
git commit -m "feat: Pydantic request/response schemas"
```

---

### Task 8: Collections Router

**Files:**
- Create: `src/agentdrive/routers/__init__.py`
- Create: `src/agentdrive/routers/collections.py`
- Modify: `src/agentdrive/main.py`
- Test: `tests/test_collections.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_collections.py
import pytest
import pytest_asyncio

from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key


TEST_API_KEY = "sk-test-key-collections"


@pytest_asyncio.fixture
async def authed_client(client, db_session):
    tenant = Tenant(name="Test Tenant", api_key_hash=hash_api_key(TEST_API_KEY))
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    return client, tenant


@pytest.mark.asyncio
async def test_create_collection(authed_client):
    client, tenant = authed_client
    response = await client.post("/v1/collections", json={"name": "my-docs", "description": "Test collection"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "my-docs"
    assert data["description"] == "Test collection"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_duplicate_collection_fails(authed_client):
    client, tenant = authed_client
    await client.post("/v1/collections", json={"name": "unique-name"})
    response = await client.post("/v1/collections", json={"name": "unique-name"})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_collections(authed_client):
    client, tenant = authed_client
    await client.post("/v1/collections", json={"name": "col-a"})
    await client.post("/v1/collections", json={"name": "col-b"})
    response = await client.get("/v1/collections")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_delete_collection(authed_client):
    client, tenant = authed_client
    create = await client.post("/v1/collections", json={"name": "to-delete"})
    col_id = create.json()["id"]
    response = await client.delete(f"/v1/collections/{col_id}")
    assert response.status_code == 204
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_collections.py -v`
Expected: FAIL

- [ ] **Step 3: Implement collections router**

```python
# src/agentdrive/routers/__init__.py
```

```python
# src/agentdrive/routers/collections.py
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.db.session import get_session
from agentdrive.dependencies import get_current_tenant
from agentdrive.models.collection import Collection
from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.schemas.collections import (
    CollectionCreate,
    CollectionListResponse,
    CollectionResponse,
)

router = APIRouter(prefix="/v1/collections", tags=["collections"])


@router.post("", status_code=201, response_model=CollectionResponse)
async def create_collection(
    body: CollectionCreate,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    collection = Collection(
        tenant_id=tenant.id,
        name=body.name,
        description=body.description,
    )
    session.add(collection)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail=f"Collection '{body.name}' already exists")
    await session.refresh(collection)
    return CollectionResponse.model_validate(collection)


@router.get("", response_model=CollectionListResponse)
async def list_collections(
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Collection).where(Collection.tenant_id == tenant.id).order_by(Collection.created_at)
    )
    collections = result.scalars().all()
    return CollectionListResponse(
        collections=[CollectionResponse.model_validate(c) for c in collections],
        total=len(collections),
    )


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Collection).where(
            Collection.id == collection_id, Collection.tenant_id == tenant.id
        )
    )
    collection = result.scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    await session.delete(collection)
    await session.commit()
```

- [ ] **Step 4: Wire router into main.py**

```python
# src/agentdrive/main.py
from fastapi import FastAPI

from agentdrive.config import settings
from agentdrive.routers import collections


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agent Drive",
        version="0.1.0",
        description="Agent-native file intelligence layer",
    )

    app.include_router(collections.router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_collections.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/routers/ src/agentdrive/main.py tests/test_collections.py
git commit -m "feat: collections CRUD endpoints"
```

---

### Task 9: Files Router (Upload + Status + List + Delete)

**Files:**
- Create: `src/agentdrive/routers/files.py`
- Modify: `src/agentdrive/main.py`
- Test: `tests/test_files.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_files.py
import io
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key


TEST_API_KEY = "sk-test-key-files"


@pytest_asyncio.fixture
async def authed_client(client, db_session):
    tenant = Tenant(name="Test Tenant", api_key_hash=hash_api_key(TEST_API_KEY))
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    return client, tenant


@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_upload_file(mock_storage_cls, authed_client):
    client, tenant = authed_client
    mock_storage = MagicMock()
    mock_storage.upload.return_value = "tenants/abc/files/def/test.pdf"
    mock_storage_cls.return_value = mock_storage

    response = await client.post(
        "/v1/files",
        files={"file": ("test.pdf", b"fake pdf content", "application/pdf")},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["filename"] == "test.pdf"
    assert data["content_type"] == "pdf"
    assert data["status"] == "pending"
    assert "id" in data


@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_upload_file_to_collection(mock_storage_cls, authed_client):
    client, tenant = authed_client
    mock_storage = MagicMock()
    mock_storage.upload.return_value = "path"
    mock_storage_cls.return_value = mock_storage

    col = await client.post("/v1/collections", json={"name": "test-col"})
    col_id = col.json()["id"]

    response = await client.post(
        "/v1/files",
        files={"file": ("test.md", b"# Hello", "text/markdown")},
        data={"collection": col_id},
    )
    assert response.status_code == 202
    assert response.json()["content_type"] == "markdown"


@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_get_file_status(mock_storage_cls, authed_client):
    client, tenant = authed_client
    mock_storage = MagicMock()
    mock_storage.upload.return_value = "path"
    mock_storage_cls.return_value = mock_storage

    upload = await client.post(
        "/v1/files",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    file_id = upload.json()["id"]

    response = await client.get(f"/v1/files/{file_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_list_files(mock_storage_cls, authed_client):
    client, tenant = authed_client
    mock_storage = MagicMock()
    mock_storage.upload.return_value = "path"
    mock_storage_cls.return_value = mock_storage

    await client.post("/v1/files", files={"file": ("a.txt", b"a", "text/plain")})
    await client.post("/v1/files", files={"file": ("b.txt", b"b", "text/plain")})

    response = await client.get("/v1/files")
    assert response.status_code == 200
    assert response.json()["total"] >= 2


@pytest.mark.asyncio
@patch("agentdrive.routers.files.StorageService")
async def test_delete_file(mock_storage_cls, authed_client):
    client, tenant = authed_client
    mock_storage = MagicMock()
    mock_storage.upload.return_value = "path"
    mock_storage_cls.return_value = mock_storage

    upload = await client.post("/v1/files", files={"file": ("del.txt", b"x", "text/plain")})
    file_id = upload.json()["id"]

    response = await client.delete(f"/v1/files/{file_id}")
    assert response.status_code == 204
    mock_storage.delete.assert_called_once()


@pytest.mark.asyncio
async def test_upload_too_large_rejected(authed_client):
    client, tenant = authed_client
    # 33MB file exceeds 32MB limit
    big_file = b"x" * (33 * 1024 * 1024)
    response = await client.post(
        "/v1/files",
        files={"file": ("big.bin", big_file, "application/octet-stream")},
    )
    assert response.status_code == 413
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_files.py -v`
Expected: FAIL

- [ ] **Step 3: Implement files router**

```python
# src/agentdrive/routers/files.py
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.config import settings
from agentdrive.db.session import get_session
from agentdrive.dependencies import get_current_tenant
from agentdrive.models.file import File as FileModel
from agentdrive.models.tenant import Tenant
from agentdrive.schemas.files import FileDetailResponse, FileListResponse, FileUploadResponse
from agentdrive.services.file_type import detect_content_type
from agentdrive.services.storage import StorageService

router = APIRouter(prefix="/v1/files", tags=["files"])


@router.post("", status_code=202, response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    collection: uuid.UUID | None = Form(None),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    data = await file.read()

    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File exceeds 32MB limit")

    content_type = detect_content_type(file.filename or "unknown", file.content_type)
    file_id = uuid.uuid4()

    storage = StorageService()
    gcs_path = storage.upload(tenant.id, file_id, file.filename or "unknown", data, file.content_type or "")

    file_record = FileModel(
        id=file_id,
        tenant_id=tenant.id,
        collection_id=collection,
        filename=file.filename or "unknown",
        content_type=content_type,
        gcs_path=gcs_path,
        file_size=len(data),
        status="pending",
    )
    session.add(file_record)
    await session.commit()
    await session.refresh(file_record)

    return FileUploadResponse.model_validate(file_record)


@router.get("/{file_id}", response_model=FileDetailResponse)
async def get_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(FileModel).where(FileModel.id == file_id, FileModel.tenant_id == tenant.id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    return FileDetailResponse.model_validate(file_record)


@router.get("", response_model=FileListResponse)
async def list_files(
    collection: uuid.UUID | None = None,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    query = select(FileModel).where(FileModel.tenant_id == tenant.id)
    if collection:
        query = query.where(FileModel.collection_id == collection)
    query = query.order_by(FileModel.created_at.desc())

    result = await session.execute(query)
    files = result.scalars().all()
    return FileListResponse(
        files=[FileDetailResponse.model_validate(f) for f in files],
        total=len(files),
    )


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(FileModel).where(FileModel.id == file_id, FileModel.tenant_id == tenant.id)
    )
    file_record = result.scalar_one_or_none()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    storage = StorageService()
    storage.delete(file_record.gcs_path)

    await session.delete(file_record)
    await session.commit()
```

- [ ] **Step 4: Wire files router into main.py**

```python
# src/agentdrive/main.py
from fastapi import FastAPI

from agentdrive.config import settings
from agentdrive.routers import collections, files


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agent Drive",
        version="0.1.0",
        description="Agent-native file intelligence layer",
    )

    app.include_router(collections.router)
    app.include_router(files.router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "environment": settings.environment}

    return app


app = create_app()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_files.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/routers/files.py src/agentdrive/main.py tests/test_files.py
git commit -m "feat: file upload, status, list, and delete endpoints"
```

---

### Task 10: Dockerfile

**Files:**
- Create: `Dockerfile`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

COPY alembic/ alembic/
COPY alembic.ini .

EXPOSE 8080

CMD ["uvicorn", "agentdrive.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Build and verify**

Run: `docker build -t agentdrive:dev .`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat: Dockerfile for Cloud Run deployment"
```

---

## Summary

After completing all 10 tasks, you will have:

- FastAPI app with health endpoint
- Pydantic config from environment variables
- Postgres + pgvector schema via Alembic migrations
- API key authentication (bcrypt)
- File type detection (extension + MIME)
- GCS storage service (upload/download/delete)
- Collections CRUD endpoints (`POST/GET/DELETE /v1/collections`)
- Files endpoints (`POST/GET/DELETE /v1/files`)
- Pydantic request/response schemas
- Docker image for Cloud Run
- Test suite covering all of the above

**Next plan:** Chunking Engine (Docling, tree-sitter, heading-based parsers, context prepending, parent-child hierarchy)
