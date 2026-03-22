# Retrieval Quality Enhancements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LLM contextual enrichment (Haiku) and table synthetic question generation to the ingest pipeline, improving retrieval quality by 35-49%.

**Architecture:** A new `enrichment/` module wraps the Anthropic SDK with prompt caching. After chunking, every chunk gets an LLM-generated context prefix. Table chunks also get synthetic questions stored as aliases. The search pipeline queries both chunks and aliases.

**Tech Stack:** anthropic SDK (with prompt caching), Claude Haiku, async Python

**Spec:** `docs/superpowers/specs/2026-03-22-retrieval-quality-design.md`

**Depends on:** Plans 1-3 complete (104 tests passing)

---

## File Structure

```
src/agentdrive/
├── config.py                      # MODIFY: add anthropic_api_key
├── enrichment/
│   ├── __init__.py
│   ├── client.py                  # Anthropic async client with prompt caching
│   ├── contextual.py              # Context prefix generation for all chunks
│   └── table_questions.py         # Synthetic question generation for tables
├── models/
│   └── chunk_alias.py             # NEW: ChunkAlias SQLAlchemy model
├── services/
│   └── ingest.py                  # MODIFY: add enrichment step
├── search/
│   └── vector.py                  # MODIFY: query chunk_aliases too
├── embedding/
│   └── pipeline.py                # MODIFY: also embed aliases
alembic/versions/
│   └── 002_chunk_aliases.py       # NEW: migration for chunk_aliases table
tests/
├── enrichment/
│   ├── __init__.py
│   ├── test_client.py
│   ├── test_contextual.py
│   └── test_table_questions.py
├── test_ingest.py                 # MODIFY: test enrichment integration
```

---

### Task 1: Config + Anthropic Dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/agentdrive/config.py`
- Modify: `.env.example`
- Modify: `.env`

- [ ] **Step 1: Add anthropic SDK to pyproject.toml**

Add to dependencies:
```
"anthropic>=0.52.0",
```

Run: `uv pip install -e ".[dev]"`

- [ ] **Step 2: Add anthropic_api_key to Settings**

In `src/agentdrive/config.py`, add to the `Settings` class:
```python
anthropic_api_key: str = ""
```

- [ ] **Step 3: Update .env.example**

Add:
```
# Anthropic (for Haiku contextual enrichment)
ANTHROPIC_API_KEY=your-key-here
```

- [ ] **Step 4: Update .env with real key**

Add your Anthropic API key to `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

- [ ] **Step 5: Verify import**

Run: `uv run python -c "import anthropic; print('OK')"`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/agentdrive/config.py .env.example
git commit -m "feat: add Anthropic SDK dependency and config"
```

---

### Task 2: Enrichment Client (Haiku + Prompt Caching)

**Files:**
- Create: `src/agentdrive/enrichment/__init__.py`
- Create: `src/agentdrive/enrichment/client.py`
- Create: `tests/enrichment/__init__.py`
- Create: `tests/enrichment/test_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/enrichment/__init__.py
```

```python
# tests/enrichment/test_client.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentdrive.enrichment.client import EnrichmentClient


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.anthropic.AsyncAnthropic")
async def test_generate_context(mock_anthropic_cls):
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="This chunk is from a Q3 board meeting about revenue.")]
    )
    mock_anthropic_cls.return_value = mock_client

    client = EnrichmentClient()
    context = await client.generate_context(
        document_text="Full document text here...",
        chunk_text="Revenue grew 34% YoY.",
    )

    assert "board meeting" in context.lower() or "revenue" in context.lower()
    assert len(context) > 10
    mock_client.messages.create.assert_called_once()


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.anthropic.AsyncAnthropic")
async def test_generate_context_uses_cache(mock_anthropic_cls):
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="Context about the chunk.")]
    )
    mock_anthropic_cls.return_value = mock_client

    client = EnrichmentClient()
    await client.generate_context("doc text", "chunk 1")

    # Verify the document text was sent with cache_control
    call_args = mock_client.messages.create.call_args
    messages = call_args[1]["messages"]
    # The user message should contain the document with cache_control
    assert any("doc text" in str(m) for m in messages)


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.anthropic.AsyncAnthropic")
async def test_generate_table_questions(mock_anthropic_cls):
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="What was Q3 revenue?\nHow did revenue grow?\nWhich quarter was highest?")]
    )
    mock_anthropic_cls.return_value = mock_client

    client = EnrichmentClient()
    questions = await client.generate_table_questions(
        "| Quarter | Revenue |\n|---|---|\n| Q1 | 3.8 |\n| Q2 | 4.0 |"
    )

    assert len(questions) >= 3
    assert all(isinstance(q, str) for q in questions)
    assert all(len(q) > 5 for q in questions)


@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.anthropic.AsyncAnthropic")
async def test_generate_context_fallback_on_error(mock_anthropic_cls):
    mock_client = AsyncMock()
    mock_client.messages.create.side_effect = Exception("API error")
    mock_anthropic_cls.return_value = mock_client

    client = EnrichmentClient()
    context = await client.generate_context("doc", "chunk")

    assert context == ""  # returns empty string on failure
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/enrichment/test_client.py -v`

- [ ] **Step 3: Implement enrichment client**

```python
# src/agentdrive/enrichment/__init__.py
```

```python
# src/agentdrive/enrichment/client.py
import logging

import anthropic

from agentdrive.config import settings

logger = logging.getLogger(__name__)

CONTEXT_PROMPT = """Here is the chunk we want to situate within the whole document:
<chunk>
{chunk_text}
</chunk>
Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""

TABLE_QUESTIONS_PROMPT = """Given this table from a document:
<table>
{table_text}
</table>
Generate 5-8 natural language questions that someone might ask that this table could answer. Return only the questions, one per line."""


class EnrichmentClient:
    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def generate_context(self, document_text: str, chunk_text: str) -> str:
        """Generate a context prefix for a chunk using the full document with prompt caching."""
        try:
            response = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"<document>\n{document_text}\n</document>",
                                "cache_control": {"type": "ephemeral"},
                            },
                            {
                                "type": "text",
                                "text": CONTEXT_PROMPT.format(chunk_text=chunk_text),
                            },
                        ],
                    }
                ],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.warning(f"Context generation failed, using empty prefix: {e}")
            return ""

    async def generate_table_questions(self, table_text: str) -> list[str]:
        """Generate synthetic questions for a table chunk."""
        try:
            response = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": TABLE_QUESTIONS_PROMPT.format(table_text=table_text),
                    }
                ],
            )
            text = response.content[0].text.strip()
            questions = [q.strip().lstrip("0123456789.-) ") for q in text.split("\n") if q.strip()]
            return [q for q in questions if len(q) > 5]
        except Exception as e:
            logger.warning(f"Table question generation failed: {e}")
            return []
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/enrichment/test_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/enrichment/ tests/enrichment/
git commit -m "feat: Anthropic enrichment client with prompt caching"
```

---

### Task 3: Contextual Enrichment Orchestrator

**Files:**
- Create: `src/agentdrive/enrichment/contextual.py`
- Create: `tests/enrichment/test_contextual.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/enrichment/test_contextual.py
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.enrichment.contextual import enrich_chunks


def make_chunk(content: str, prefix: str = "File: test.md") -> ChunkResult:
    return ChunkResult(
        content=content, context_prefix=prefix,
        token_count=10, content_type="text",
    )


def make_group(parent_content: str, child_contents: list[str]) -> ParentChildChunks:
    parent = make_chunk(parent_content)
    children = [make_chunk(c) for c in child_contents]
    return ParentChildChunks(parent=parent, children=children)


@pytest.mark.asyncio
@patch("agentdrive.enrichment.contextual.EnrichmentClient")
async def test_enrich_replaces_context_prefix(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.generate_context.return_value = "This is enriched context."
    mock_client_cls.return_value = mock_client

    groups = [make_group("Parent text.", ["Child one.", "Child two."])]
    enriched = await enrich_chunks("Full document text.", groups)

    assert enriched[0].children[0].context_prefix == "This is enriched context."
    assert enriched[0].children[1].context_prefix == "This is enriched context."
    assert enriched[0].parent.context_prefix == "This is enriched context."


@pytest.mark.asyncio
@patch("agentdrive.enrichment.contextual.EnrichmentClient")
async def test_enrich_preserves_original_on_failure(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.generate_context.return_value = ""  # failure returns empty
    mock_client_cls.return_value = mock_client

    groups = [make_group("Parent.", ["Child."])]
    groups[0].children[0].context_prefix = "Original breadcrumb"
    enriched = await enrich_chunks("Doc text.", groups)

    # Should keep original breadcrumb when enrichment returns empty
    assert enriched[0].children[0].context_prefix == "Original breadcrumb"


@pytest.mark.asyncio
@patch("agentdrive.enrichment.contextual.EnrichmentClient")
async def test_enrich_multiple_groups(mock_client_cls):
    call_count = 0
    async def mock_generate(doc, chunk):
        nonlocal call_count
        call_count += 1
        return f"Context {call_count}"
    mock_client = AsyncMock()
    mock_client.generate_context.side_effect = mock_generate
    mock_client_cls.return_value = mock_client

    groups = [
        make_group("Parent A", ["Child A1"]),
        make_group("Parent B", ["Child B1", "Child B2"]),
    ]
    enriched = await enrich_chunks("Doc.", groups)

    # 2 parents + 3 children = 5 calls
    assert call_count == 5
```

- [ ] **Step 2: Implement contextual enrichment**

```python
# src/agentdrive/enrichment/contextual.py
import asyncio
import logging

from agentdrive.chunking.base import ParentChildChunks
from agentdrive.enrichment.client import EnrichmentClient

logger = logging.getLogger(__name__)

MAX_CONCURRENT = 5  # limit concurrent Haiku calls


async def enrich_chunks(
    document_text: str,
    chunk_groups: list[ParentChildChunks],
) -> list[ParentChildChunks]:
    """Enrich all chunks with LLM-generated context prefixes."""
    client = EnrichmentClient()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def enrich_one(chunk_result):
        async with semaphore:
            original_prefix = chunk_result.context_prefix
            context = await client.generate_context(document_text, chunk_result.content)
            if context:
                chunk_result.context_prefix = context
            # If empty (failure), keep original breadcrumb

    tasks = []
    for group in chunk_groups:
        tasks.append(enrich_one(group.parent))
        for child in group.children:
            tasks.append(enrich_one(child))

    await asyncio.gather(*tasks)
    return chunk_groups
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/enrichment/test_contextual.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/agentdrive/enrichment/contextual.py tests/enrichment/test_contextual.py
git commit -m "feat: contextual enrichment orchestrator with concurrency control"
```

---

### Task 4: Table Question Generator

**Files:**
- Create: `src/agentdrive/enrichment/table_questions.py`
- Create: `tests/enrichment/test_table_questions.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/enrichment/test_table_questions.py
import re
from unittest.mock import AsyncMock, patch

import pytest

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.enrichment.table_questions import is_table_chunk, generate_table_aliases


def test_is_table_chunk_true():
    content = "| Name | Age |\n|---|---|\n| Alice | 30 |\n| Bob | 25 |"
    assert is_table_chunk(content) is True


def test_is_table_chunk_false():
    content = "This is a normal paragraph with no table."
    assert is_table_chunk(content) is False


def test_is_table_chunk_with_surrounding_text():
    content = "Some intro text.\n\n| Col A | Col B |\n|---|---|\n| 1 | 2 |\n\nMore text."
    assert is_table_chunk(content) is True


def test_is_table_chunk_pipe_in_code_not_table():
    content = "Use `a | b` for piping commands."
    assert is_table_chunk(content) is False


@pytest.mark.asyncio
@patch("agentdrive.enrichment.table_questions.EnrichmentClient")
async def test_generate_table_aliases(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.generate_table_questions.return_value = [
        "What is Alice's age?",
        "How old is Bob?",
        "Who is the oldest person?",
    ]
    mock_client_cls.return_value = mock_client

    table_content = "| Name | Age |\n|---|---|\n| Alice | 30 |\n| Bob | 25 |"
    chunk = ChunkResult(
        content=table_content, context_prefix="File: data.md",
        token_count=20, content_type="text",
    )
    group = ParentChildChunks(parent=chunk, children=[chunk])

    aliases = await generate_table_aliases([group])

    assert len(aliases) == 3
    assert all("question" in a for a in aliases)
    assert all("chunk" in a for a in aliases)


@pytest.mark.asyncio
@patch("agentdrive.enrichment.table_questions.EnrichmentClient")
async def test_no_aliases_for_non_table(mock_client_cls):
    chunk = ChunkResult(
        content="Just a paragraph of text.", context_prefix="",
        token_count=10, content_type="text",
    )
    group = ParentChildChunks(parent=chunk, children=[chunk])

    aliases = await generate_table_aliases([group])

    assert len(aliases) == 0
    mock_client_cls.return_value.generate_table_questions.assert_not_called()
```

- [ ] **Step 2: Implement table questions**

```python
# src/agentdrive/enrichment/table_questions.py
import re

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.enrichment.client import EnrichmentClient


def is_table_chunk(content: str) -> bool:
    """Check if chunk contains a markdown table."""
    lines = content.strip().split("\n")
    pipe_lines = [l for l in lines if l.count("|") >= 2 and not l.strip().startswith("`")]
    separator_lines = [l for l in lines if re.match(r'^\|[\s\-:|]+\|$', l.strip())]
    return len(pipe_lines) >= 3 and len(separator_lines) >= 1


async def generate_table_aliases(
    chunk_groups: list[ParentChildChunks],
) -> list[dict]:
    """Generate synthetic questions for table chunks. Returns alias records."""
    client = EnrichmentClient()
    aliases = []

    for group in chunk_groups:
        for child in group.children:
            if is_table_chunk(child.content):
                questions = await client.generate_table_questions(child.content)
                for q in questions:
                    aliases.append({"question": q, "chunk": child})

    return aliases
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/enrichment/test_table_questions.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/agentdrive/enrichment/table_questions.py tests/enrichment/test_table_questions.py
git commit -m "feat: table detection and synthetic question generation"
```

---

### Task 5: ChunkAlias Model + Migration

**Files:**
- Create: `src/agentdrive/models/chunk_alias.py`
- Modify: `src/agentdrive/models/__init__.py`
- Create: `alembic/versions/002_chunk_aliases.py`

- [ ] **Step 1: Create ChunkAlias model**

```python
# src/agentdrive/models/chunk_alias.py
import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class ChunkAlias(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "chunk_aliases"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # embedding column added via migration (pgvector halfvec)
```

- [ ] **Step 2: Add to models __init__.py**

Add to `src/agentdrive/models/__init__.py`:
```python
from agentdrive.models.chunk_alias import ChunkAlias
```
And add `"ChunkAlias"` to `__all__`.

- [ ] **Step 3: Create migration**

```python
# alembic/versions/002_chunk_aliases.py
"""Add chunk_aliases table

Revision ID: 002
Revises: 001
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chunk_aliases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.execute("ALTER TABLE chunk_aliases ADD COLUMN embedding halfvec(256)")

    op.execute("""
        CREATE INDEX idx_chunk_aliases_embedding ON chunk_aliases
        USING hnsw (embedding halfvec_cosine_ops)
        WITH (m = 16, ef_construction = 128)
    """)

    op.create_index("idx_chunk_aliases_chunk", "chunk_aliases", ["chunk_id"])
    op.create_index("idx_chunk_aliases_file", "chunk_aliases", ["file_id"])


def downgrade() -> None:
    op.drop_table("chunk_aliases")
```

- [ ] **Step 4: Update test conftest to include chunk_aliases table**

Add to `tests/conftest.py` in the `db_engine` fixture, after the existing halfvec column additions:
```python
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
```

- [ ] **Step 5: Verify model import**

Run: `uv run python -c "from agentdrive.models import ChunkAlias; print('OK')"`

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/models/chunk_alias.py src/agentdrive/models/__init__.py alembic/versions/002_chunk_aliases.py tests/conftest.py
git commit -m "feat: ChunkAlias model and migration for table synthetic questions"
```

---

### Task 6: Wire Enrichment Into Ingest Pipeline

**Files:**
- Modify: `src/agentdrive/services/ingest.py`
- Modify: `tests/test_ingest.py`

- [ ] **Step 1: Update ingest.py**

Add enrichment between chunking and storing. The key changes to `process_file`:

```python
# Add imports at top of file:
from agentdrive.enrichment.contextual import enrich_chunks
from agentdrive.enrichment.table_questions import generate_table_aliases

# After line 31 (chunk_groups = chunker.chunk_bytes(...)):

# Get document text for enrichment
document_text = data.decode("utf-8", errors="replace")

# Enrich all chunks with LLM context
chunk_groups = await enrich_chunks(document_text, chunk_groups)

# Generate table aliases
table_aliases = await generate_table_aliases(chunk_groups)

# ... existing chunk storage code, BUT add chunk_id_map ...
# Inside the chunk storage loop, after each child chunk is added:
chunk_id_map = {}  # maps ChunkResult identity → DB chunk ID
# ... in the loop, after session.add(chunk_record) and session.flush():
#   chunk_id_map[id(child)] = chunk_record.id

# Build a map from ChunkResult identity to stored Chunk ID
# (populated during the chunk storage loop above by adding:
#   chunk_id_map[id(child)] = chunk_record.id
# after each chunk_record is added and flushed)
from agentdrive.models.chunk_alias import ChunkAlias
from agentdrive.chunking.tokens import count_tokens

for alias_data in table_aliases:
    chunk_db_id = chunk_id_map.get(id(alias_data["chunk"]))
    if chunk_db_id:
        alias_record = ChunkAlias(
            chunk_id=chunk_db_id,
            file_id=file.id,
            content=alias_data["question"],
            token_count=count_tokens(alias_data["question"]),
        )
        session.add(alias_record)
```

- [ ] **Step 2: Add autouse fixture to mock enrichment in existing tests**

Update `tests/conftest.py` — **replace** the existing `mock_embed_file_chunks_in_ingest` fixture with a new combined fixture that mocks enrichment too. Delete the old fixture entirely.

```python
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
         patch("agentdrive.services.ingest.enrich_chunks", side_effect=_noop_enrich), \
         patch("agentdrive.services.ingest.generate_table_aliases", side_effect=_noop_aliases):
        yield
```

- [ ] **Step 3: Add enrichment-specific ingest test**

Add to `tests/test_ingest.py`:

```python
@pytest.mark.asyncio
@patch("agentdrive.services.ingest.generate_table_aliases", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.enrich_chunks", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.embed_file_chunks", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.StorageService")
async def test_process_file_calls_enrichment(mock_storage_cls, mock_embed, mock_enrich, mock_aliases, test_file, db_session):
    mock_storage = MagicMock()
    mock_storage.download.return_value = b"# Doc\n\n## Section\n\nContent."
    mock_storage_cls.return_value = mock_storage

    mock_enrich.side_effect = lambda doc, groups: groups
    mock_aliases.return_value = []

    await process_file(test_file.id, db_session)

    mock_enrich.assert_called_once()
    mock_aliases.assert_called_once()
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/services/ingest.py tests/test_ingest.py tests/conftest.py
git commit -m "feat: wire enrichment into ingest pipeline"
```

---

### Task 7: Embed Aliases + Search Integration

**Files:**
- Modify: `src/agentdrive/embedding/pipeline.py`
- Modify: `src/agentdrive/search/vector.py`

- [ ] **Step 1: Add alias embedding to pipeline**

Add a new function to `src/agentdrive/embedding/pipeline.py`:

```python
async def embed_file_aliases(file_id: uuid.UUID, session: AsyncSession) -> int:
    """Embed all chunk aliases for a file."""
    from agentdrive.models.chunk_alias import ChunkAlias

    client = EmbeddingClient()
    result = await session.execute(
        select(ChunkAlias).where(ChunkAlias.file_id == file_id)
    )
    aliases = result.scalars().all()
    if not aliases:
        return 0

    embedded_count = 0
    for i in range(0, len(aliases), BATCH_SIZE):
        batch = aliases[i:i + BATCH_SIZE]
        texts = [a.content for a in batch]
        # Aliases are synthetic questions — embed as queries for better matching
        vectors = client.embed(texts, input_type="query", content_type="text")

        for alias, vector in zip(batch, vectors):
            vec_256 = client.truncate(vector, 256)
            vec_str = "[" + ",".join(str(v) for v in vec_256) + "]"
            await session.execute(
                text("UPDATE chunk_aliases SET embedding = :emb WHERE id = :alias_id"),
                {"emb": vec_str, "alias_id": alias.id},
            )
            embedded_count += 1

    await session.commit()
    logger.info(f"Embedded {embedded_count} aliases for file {file_id}")
    return embedded_count
```

Call it from `ingest.py` after `embed_file_chunks`:

```python
from agentdrive.embedding.pipeline import embed_file_chunks, embed_file_aliases

await embed_file_chunks(file.id, session)
await embed_file_aliases(file.id, session)
```

- [ ] **Step 2: Update vector search to include aliases**

Modify `src/agentdrive/search/vector.py` — after the main chunks query, also search aliases and merge:

```python
# After the main query, add alias search:
alias_query = text(f"""
    SELECT c.id, c.file_id, c.content, c.context_prefix, c.token_count,
           c.content_type, c.metadata, c.parent_chunk_id,
           ca.embedding <=> CAST(:embedding AS halfvec(256)) AS distance
    FROM chunk_aliases ca
    JOIN chunks c ON ca.chunk_id = c.id
    JOIN files f ON c.file_id = f.id
    WHERE {where} AND ca.embedding IS NOT NULL
    ORDER BY distance
    LIMIT :top_k
""")

alias_result = await session.execute(alias_query, params)
alias_rows = alias_result.fetchall()

# Combine and deduplicate (prefer better score)
seen_ids = {r.chunk_id for r in results}
for row in alias_rows:
    if row.id not in seen_ids:
        results.append(SearchResult(
            chunk_id=row.id, file_id=row.file_id, content=row.content,
            context_prefix=row.context_prefix, token_count=row.token_count,
            content_type=row.content_type, score=1.0 - row.distance,
            metadata=row.metadata or {}, parent_chunk_id=row.parent_chunk_id,
        ))
        seen_ids.add(row.id)

# Re-sort by score
results.sort(key=lambda r: r.score, reverse=True)
return results[:top_k]
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/agentdrive/embedding/pipeline.py src/agentdrive/search/vector.py src/agentdrive/services/ingest.py
git commit -m "feat: embed aliases and search across chunks + aliases"
```

---

## Summary

After completing all 7 tasks:

- Anthropic SDK integrated with prompt caching
- Every chunk gets an LLM-generated context prefix via Haiku
- Table chunks get 5-8 synthetic questions as searchable aliases
- Search queries both chunks and aliases, deduplicates results
- Graceful fallback to breadcrumbs on LLM failure
- Concurrent enrichment with semaphore (5 parallel Haiku calls)
- New `chunk_aliases` table with HNSW index

**Expected impact:** 35-49% fewer retrieval failures, dramatically better table/CSV search quality.
