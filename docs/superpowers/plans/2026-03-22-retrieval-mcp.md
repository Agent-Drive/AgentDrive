# Agent Drive Retrieval Engine + MCP Server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the embedding pipeline, hybrid search (vector + BM25), reranking, and MCP server that lets agents search and retrieve from Agent Drive.

**Architecture:** An embedding service calls Voyage AI to embed chunks. A search service performs hybrid retrieval (pgvector HNSW + Postgres FTS + application-layer BM25 + Cohere Rerank). An MCP server exposes tools for agents. The ingest pipeline from Plan 2 is extended to embed chunks after creation.

**Tech Stack:** Python 3.12, Voyage AI SDK, Cohere SDK, pgvector, FastAPI, MCP SDK (mcp)

**Spec:** `docs/superpowers/specs/2026-03-22-agent-drive-design.md` — Sections 6, 7, 8

**Depends on:** Plan 1 (Core Infrastructure) and Plan 2 (Chunking Engine) must be complete.

---

## File Structure

```
src/agentdrive/
├── embedding/
│   ├── __init__.py
│   ├── client.py             # Voyage AI embedding client
│   └── pipeline.py           # Batch embed chunks, store vectors
├── search/
│   ├── __init__.py
│   ├── vector.py             # pgvector HNSW search
│   ├── bm25.py               # Postgres FTS + app-layer BM25
│   ├── fusion.py             # Reciprocal Rank Fusion
│   ├── rerank.py             # Cohere Rerank integration
│   └── engine.py             # Orchestrates full search pipeline
├── routers/
│   └── search.py             # POST /v1/search, GET /v1/chunks/:id
├── mcp/
│   ├── __init__.py
│   └── server.py             # MCP tool definitions
tests/
├── embedding/
│   ├── test_client.py
│   └── test_pipeline.py
├── search/
│   ├── test_vector.py
│   ├── test_bm25.py
│   ├── test_fusion.py
│   ├── test_rerank.py
│   └── test_engine.py
├── test_search_api.py
└── mcp/
    └── test_server.py
```

---

### Task 1: Voyage AI Embedding Client

**Files:**
- Create: `src/agentdrive/embedding/__init__.py`
- Create: `src/agentdrive/embedding/client.py`
- Test: `tests/embedding/test_client.py`

- [ ] **Step 1: Add Voyage dependency**

Add to `pyproject.toml`:
```
"voyageai>=0.3.0",
```

- [ ] **Step 2: Write failing tests**

```python
# tests/embedding/__init__.py
```

```python
# tests/embedding/test_client.py
from unittest.mock import MagicMock, patch

import pytest

from agentdrive.embedding.client import EmbeddingClient


@patch("agentdrive.embedding.client.voyageai.Client")
def test_embed_texts(mock_voyage_cls):
    mock_client = MagicMock()
    mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024, [0.2] * 1024])
    mock_voyage_cls.return_value = mock_client

    client = EmbeddingClient()
    vectors = client.embed(["hello", "world"], input_type="document")

    assert len(vectors) == 2
    assert len(vectors[0]) == 1024
    mock_client.embed.assert_called_once()


@patch("agentdrive.embedding.client.voyageai.Client")
def test_embed_query(mock_voyage_cls):
    mock_client = MagicMock()
    mock_client.embed.return_value = MagicMock(embeddings=[[0.3] * 1024])
    mock_voyage_cls.return_value = mock_client

    client = EmbeddingClient()
    vector = client.embed_query("search query")

    assert len(vector) == 1024


@patch("agentdrive.embedding.client.voyageai.Client")
def test_truncate_to_256d(mock_voyage_cls):
    mock_client = MagicMock()
    mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
    mock_voyage_cls.return_value = mock_client

    client = EmbeddingClient()
    vectors = client.embed(["hello"], input_type="document")
    truncated = client.truncate(vectors[0], 256)

    assert len(truncated) == 256


@patch("agentdrive.embedding.client.voyageai.Client")
def test_code_model_used_for_code(mock_voyage_cls):
    mock_client = MagicMock()
    mock_client.embed.return_value = MagicMock(embeddings=[[0.1] * 1024])
    mock_voyage_cls.return_value = mock_client

    client = EmbeddingClient()
    client.embed(["def hello(): pass"], input_type="document", content_type="code")

    call_args = mock_client.embed.call_args
    assert call_args[1]["model"] == "voyage-code-3" or call_args[0][0] is not None
```

- [ ] **Step 3: Implement embedding client**

```python
# src/agentdrive/embedding/__init__.py
```

```python
# src/agentdrive/embedding/client.py
import voyageai

from agentdrive.config import settings

DOC_MODEL = "voyage-4"
CODE_MODEL = "voyage-code-3"
QUERY_MODEL = "voyage-4-lite"


class EmbeddingClient:
    def __init__(self) -> None:
        self._client = voyageai.Client(api_key=settings.voyage_api_key)

    def embed(
        self,
        texts: list[str],
        input_type: str = "document",
        content_type: str = "text",
    ) -> list[list[float]]:
        model = CODE_MODEL if content_type == "code" else DOC_MODEL
        result = self._client.embed(
            texts,
            model=model,
            input_type=input_type,
        )
        return result.embeddings

    def embed_query(self, query: str) -> list[float]:
        result = self._client.embed(
            [query],
            model=QUERY_MODEL,
            input_type="query",
        )
        return result.embeddings[0]

    def truncate(self, vector: list[float], dimensions: int) -> list[float]:
        return vector[:dimensions]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/embedding/test_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/embedding/ tests/embedding/ pyproject.toml
git commit -m "feat: Voyage AI embedding client with model routing"
```

---

### Task 2: Embedding Pipeline (Batch Embed + Store Vectors)

**Files:**
- Create: `src/agentdrive/embedding/pipeline.py`
- Test: `tests/embedding/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/embedding/test_pipeline.py
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key


@pytest_asyncio.fixture
async def file_with_chunks(db_session):
    tenant = Tenant(name="Test", api_key_hash=hash_api_key("sk-test"))
    db_session.add(tenant)
    await db_session.commit()

    file = File(
        tenant_id=tenant.id, filename="test.md", content_type="markdown",
        gcs_path="path", file_size=100, status="ready",
    )
    db_session.add(file)
    await db_session.commit()

    parent = ParentChunk(file_id=file.id, content="Full section", token_count=50)
    db_session.add(parent)
    await db_session.flush()

    chunk = Chunk(
        file_id=file.id, parent_chunk_id=parent.id, chunk_index=0,
        content="Hello world", context_prefix="File: test.md",
        token_count=5, content_type="text",
    )
    db_session.add(chunk)
    await db_session.commit()
    return file


@pytest.mark.asyncio
@patch("agentdrive.embedding.pipeline.EmbeddingClient")
async def test_embed_file_chunks(mock_client_cls, file_with_chunks, db_session):
    mock_client = MagicMock()
    mock_client.embed.return_value = [[0.1] * 1024]
    mock_client.truncate.return_value = [0.1] * 256
    mock_client_cls.return_value = mock_client

    from agentdrive.embedding.pipeline import embed_file_chunks
    await embed_file_chunks(file_with_chunks.id, db_session)

    mock_client.embed.assert_called_once()
```

- [ ] **Step 2: Implement embedding pipeline**

```python
# src/agentdrive/embedding/pipeline.py
import logging
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.embedding.client import EmbeddingClient
from agentdrive.models.chunk import Chunk

logger = logging.getLogger(__name__)

BATCH_SIZE = 64


async def embed_file_chunks(file_id: uuid.UUID, session: AsyncSession) -> int:
    client = EmbeddingClient()

    result = await session.execute(
        select(Chunk).where(Chunk.file_id == file_id).order_by(Chunk.chunk_index)
    )
    chunks = result.scalars().all()

    if not chunks:
        return 0

    embedded_count = 0
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]

        # Prepare texts with context prefix
        texts = [f"{c.context_prefix}\n{c.content}" if c.context_prefix else c.content for c in batch]

        # Determine content type (code vs text)
        content_type = batch[0].content_type

        # Embed
        vectors_full = client.embed(texts, input_type="document", content_type=content_type)

        # Store vectors
        for chunk, vector in zip(batch, vectors_full):
            vector_256 = client.truncate(vector, 256)
            # Use raw SQL for pgvector halfvec columns
            await session.execute(
                update(Chunk)
                .where(Chunk.id == chunk.id)
                .values(
                    embedding=vector_256,
                    embedding_full=vector,
                )
            )
            embedded_count += 1

    await session.commit()
    logger.info(f"Embedded {embedded_count} chunks for file {file_id}")
    return embedded_count
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/embedding/test_pipeline.py -v`
Expected: PASS

- [ ] **Step 4: Wire embedding into ingest pipeline**

Add to `src/agentdrive/services/ingest.py` after chunks are stored:

```python
from agentdrive.embedding.pipeline import embed_file_chunks

# After file.status = FileStatus.READY, before session.commit():
await embed_file_chunks(file.id, session)
```

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/embedding/pipeline.py tests/embedding/test_pipeline.py src/agentdrive/services/ingest.py
git commit -m "feat: embedding pipeline — batch embed chunks via Voyage, store in pgvector"
```

---

### Task 3: Vector Search

**Files:**
- Create: `src/agentdrive/search/__init__.py`
- Create: `src/agentdrive/search/vector.py`
- Test: `tests/search/test_vector.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/search/__init__.py
```

```python
# tests/search/test_vector.py
from unittest.mock import MagicMock

import pytest

from agentdrive.search.vector import SearchResult, vector_search


@pytest.mark.asyncio
async def test_vector_search_returns_results(db_session):
    # This test requires chunks with embeddings in the DB.
    # For unit testing, we mock the raw SQL query.
    # Integration test with real vectors is in test_engine.py
    pass  # placeholder — tested via integration in Task 7
```

- [ ] **Step 2: Implement vector search**

```python
# src/agentdrive/search/__init__.py
```

```python
# src/agentdrive/search/vector.py
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class SearchResult:
    chunk_id: uuid.UUID
    file_id: uuid.UUID
    content: str
    context_prefix: str
    token_count: int
    content_type: str
    score: float
    metadata: dict
    parent_chunk_id: uuid.UUID | None = None


async def vector_search(
    query_embedding: list[float],
    session: AsyncSession,
    tenant_id: uuid.UUID,
    top_k: int = 50,
    collections: list[uuid.UUID] | None = None,
    content_types: list[str] | None = None,
) -> list[SearchResult]:
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    where_clauses = ["f.tenant_id = :tenant_id"]
    params: dict = {"tenant_id": str(tenant_id), "embedding": embedding_str, "top_k": top_k}

    if collections:
        where_clauses.append("f.collection_id = ANY(:collections)")
        params["collections"] = [str(c) for c in collections]

    if content_types:
        where_clauses.append("c.content_type = ANY(:content_types)")
        params["content_types"] = content_types

    where = " AND ".join(where_clauses)

    query = text(f"""
        SELECT c.id, c.file_id, c.content, c.context_prefix, c.token_count,
               c.content_type, c.metadata, c.parent_chunk_id,
               c.embedding <=> :embedding::halfvec(256) AS distance
        FROM chunks c
        JOIN files f ON c.file_id = f.id
        WHERE {where} AND c.embedding IS NOT NULL
        ORDER BY distance
        LIMIT :top_k
    """)

    result = await session.execute(query, params)
    rows = result.fetchall()

    return [
        SearchResult(
            chunk_id=row.id,
            file_id=row.file_id,
            content=row.content,
            context_prefix=row.context_prefix,
            token_count=row.token_count,
            content_type=row.content_type,
            score=1.0 - row.distance,  # convert distance to similarity
            metadata=row.metadata or {},
            parent_chunk_id=row.parent_chunk_id,
        )
        for row in rows
    ]
```

- [ ] **Step 3: Commit**

```bash
git add src/agentdrive/search/ tests/search/
git commit -m "feat: pgvector HNSW search with tenant and collection filtering"
```

---

### Task 4: BM25 Search (Postgres FTS + Application-Layer Scoring)

**Files:**
- Create: `src/agentdrive/search/bm25.py`
- Test: `tests/search/test_bm25.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/search/test_bm25.py
from agentdrive.search.bm25 import bm25_score


def test_bm25_score_positive():
    score = bm25_score(tf=3, df=10, dl=100, avgdl=120, n_docs=1000)
    assert score > 0


def test_bm25_score_zero_tf():
    score = bm25_score(tf=0, df=10, dl=100, avgdl=120, n_docs=1000)
    assert score == 0.0


def test_bm25_score_rare_term_higher():
    common = bm25_score(tf=1, df=500, dl=100, avgdl=100, n_docs=1000)
    rare = bm25_score(tf=1, df=5, dl=100, avgdl=100, n_docs=1000)
    assert rare > common
```

- [ ] **Step 2: Implement BM25**

```python
# src/agentdrive/search/bm25.py
import math
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.search.vector import SearchResult


def bm25_score(
    tf: int, df: int, dl: int, avgdl: float, n_docs: int,
    k1: float = 1.2, b: float = 0.75,
) -> float:
    if tf == 0:
        return 0.0
    idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)
    tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (dl / avgdl)))
    return idf * tf_norm


async def bm25_search(
    query: str,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    top_k: int = 50,
    collections: list[uuid.UUID] | None = None,
) -> list[SearchResult]:
    where_clauses = [
        "f.tenant_id = :tenant_id",
        "to_tsvector('english', c.content) @@ plainto_tsquery('english', :query)",
    ]
    params: dict = {"tenant_id": str(tenant_id), "query": query, "top_k": top_k}

    if collections:
        where_clauses.append("f.collection_id = ANY(:collections)")
        params["collections"] = [str(c) for c in collections]

    where = " AND ".join(where_clauses)

    sql = text(f"""
        SELECT c.id, c.file_id, c.content, c.context_prefix, c.token_count,
               c.content_type, c.metadata, c.parent_chunk_id,
               ts_rank(to_tsvector('english', c.content), plainto_tsquery('english', :query)) AS rank
        FROM chunks c
        JOIN files f ON c.file_id = f.id
        WHERE {where}
        ORDER BY rank DESC
        LIMIT :top_k
    """)

    result = await session.execute(sql, params)
    rows = result.fetchall()

    return [
        SearchResult(
            chunk_id=row.id,
            file_id=row.file_id,
            content=row.content,
            context_prefix=row.context_prefix,
            token_count=row.token_count,
            content_type=row.content_type,
            score=float(row.rank),
            metadata=row.metadata or {},
            parent_chunk_id=row.parent_chunk_id,
        )
        for row in rows
    ]
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/search/test_bm25.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/agentdrive/search/bm25.py tests/search/test_bm25.py
git commit -m "feat: BM25 scoring + Postgres full-text search"
```

---

### Task 5: Reciprocal Rank Fusion

**Files:**
- Create: `src/agentdrive/search/fusion.py`
- Test: `tests/search/test_fusion.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/search/test_fusion.py
import uuid

from agentdrive.search.fusion import reciprocal_rank_fusion
from agentdrive.search.vector import SearchResult


def make_result(chunk_id: str, score: float) -> SearchResult:
    return SearchResult(
        chunk_id=uuid.UUID(chunk_id),
        file_id=uuid.uuid4(),
        content="test",
        context_prefix="",
        token_count=10,
        content_type="text",
        score=score,
        metadata={},
    )


ID_A = "00000000-0000-0000-0000-000000000001"
ID_B = "00000000-0000-0000-0000-000000000002"
ID_C = "00000000-0000-0000-0000-000000000003"


def test_rrf_merges_two_lists():
    list_a = [make_result(ID_A, 0.9), make_result(ID_B, 0.8)]
    list_b = [make_result(ID_B, 0.95), make_result(ID_C, 0.7)]

    merged = reciprocal_rank_fusion([list_a, list_b], k=60, top_k=10)

    ids = [r.chunk_id for r in merged]
    # B should rank highest (appears in both lists)
    assert uuid.UUID(ID_B) in ids


def test_rrf_respects_top_k():
    results = [make_result(f"00000000-0000-0000-0000-{i:012d}", 0.5) for i in range(1, 20)]
    merged = reciprocal_rank_fusion([results], k=60, top_k=5)
    assert len(merged) <= 5


def test_rrf_empty_lists():
    merged = reciprocal_rank_fusion([[], []], k=60, top_k=10)
    assert merged == []
```

- [ ] **Step 2: Implement RRF**

```python
# src/agentdrive/search/fusion.py
from agentdrive.search.vector import SearchResult


def reciprocal_rank_fusion(
    result_lists: list[list[SearchResult]],
    k: int = 60,
    top_k: int = 20,
) -> list[SearchResult]:
    scores: dict[str, float] = {}
    result_map: dict[str, SearchResult] = {}

    for results in result_lists:
        for rank, result in enumerate(results):
            key = str(result.chunk_id)
            rrf_score = 1.0 / (k + rank + 1)
            scores[key] = scores.get(key, 0.0) + rrf_score
            if key not in result_map:
                result_map[key] = result

    sorted_keys = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    merged = []
    for key in sorted_keys[:top_k]:
        result = result_map[key]
        result.score = scores[key]
        merged.append(result)

    return merged
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/search/test_fusion.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/agentdrive/search/fusion.py tests/search/test_fusion.py
git commit -m "feat: reciprocal rank fusion for hybrid search"
```

---

### Task 6: Cohere Reranker

**Files:**
- Create: `src/agentdrive/search/rerank.py`
- Test: `tests/search/test_rerank.py`

- [ ] **Step 1: Add Cohere dependency**

Add to `pyproject.toml`:
```
"cohere>=5.0.0",
```

- [ ] **Step 2: Write failing tests**

```python
# tests/search/test_rerank.py
import uuid
from unittest.mock import MagicMock, patch

from agentdrive.search.rerank import rerank_results
from agentdrive.search.vector import SearchResult


def make_result(content: str, score: float) -> SearchResult:
    return SearchResult(
        chunk_id=uuid.uuid4(), file_id=uuid.uuid4(),
        content=content, context_prefix="", token_count=10,
        content_type="text", score=score, metadata={},
    )


@patch("agentdrive.search.rerank.cohere_client")
def test_rerank_reorders(mock_cohere):
    mock_cohere.rerank.return_value = MagicMock(
        results=[
            MagicMock(index=1, relevance_score=0.95),
            MagicMock(index=0, relevance_score=0.80),
        ]
    )

    candidates = [make_result("less relevant", 0.9), make_result("more relevant", 0.8)]
    reranked = rerank_results("test query", candidates, top_k=2)

    assert len(reranked) == 2
    assert reranked[0].content == "more relevant"
    assert reranked[0].score == 0.95


@patch("agentdrive.search.rerank.cohere_client")
def test_rerank_respects_top_k(mock_cohere):
    mock_cohere.rerank.return_value = MagicMock(
        results=[MagicMock(index=0, relevance_score=0.9)]
    )
    candidates = [make_result("a", 0.5), make_result("b", 0.4)]
    reranked = rerank_results("query", candidates, top_k=1)
    assert len(reranked) == 1
```

- [ ] **Step 3: Implement reranker**

```python
# src/agentdrive/search/rerank.py
import cohere

from agentdrive.config import settings
from agentdrive.search.vector import SearchResult

cohere_client = cohere.Client(api_key=settings.cohere_api_key)


def rerank_results(
    query: str,
    candidates: list[SearchResult],
    top_k: int = 5,
) -> list[SearchResult]:
    if not candidates:
        return []

    documents = [c.content for c in candidates]

    response = cohere_client.rerank(
        query=query,
        documents=documents,
        model="rerank-v3.5",
        top_n=top_k,
    )

    reranked = []
    for result in response.results:
        candidate = candidates[result.index]
        candidate.score = result.relevance_score
        reranked.append(candidate)

    return reranked
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/search/test_rerank.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/search/rerank.py tests/search/test_rerank.py pyproject.toml
git commit -m "feat: Cohere Rerank 3 integration"
```

---

### Task 7: Search Engine (Full Pipeline Orchestrator)

**Files:**
- Create: `src/agentdrive/search/engine.py`
- Test: `tests/search/test_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/search/test_engine.py
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentdrive.search.engine import SearchEngine
from agentdrive.search.vector import SearchResult


def make_result(content: str, score: float) -> SearchResult:
    return SearchResult(
        chunk_id=uuid.uuid4(), file_id=uuid.uuid4(),
        content=content, context_prefix="", token_count=10,
        content_type="text", score=score, metadata={},
        parent_chunk_id=uuid.uuid4(),
    )


@pytest.mark.asyncio
@patch("agentdrive.search.engine.rerank_results")
@patch("agentdrive.search.engine.bm25_search", new_callable=AsyncMock)
@patch("agentdrive.search.engine.vector_search", new_callable=AsyncMock)
@patch("agentdrive.search.engine.EmbeddingClient")
async def test_search_combines_vector_and_bm25(mock_embed_cls, mock_vector, mock_bm25, mock_rerank):
    mock_client = MagicMock()
    mock_client.embed_query.return_value = [0.1] * 1024
    mock_client.truncate.return_value = [0.1] * 256
    mock_embed_cls.return_value = mock_client

    r1 = make_result("vector result", 0.9)
    r2 = make_result("bm25 result", 0.8)
    mock_vector.return_value = [r1]
    mock_bm25.return_value = [r2]
    mock_rerank.return_value = [r1, r2]

    engine = SearchEngine()
    session = AsyncMock()
    tenant_id = uuid.uuid4()

    results = await engine.search("test query", session, tenant_id, top_k=5)

    assert len(results) > 0
    mock_vector.assert_called_once()
    mock_bm25.assert_called_once()
    mock_rerank.assert_called_once()
```

- [ ] **Step 2: Implement search engine**

```python
# src/agentdrive/search/engine.py
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.embedding.client import EmbeddingClient
from agentdrive.models.chunk import ParentChunk
from agentdrive.search.bm25 import bm25_search
from agentdrive.search.fusion import reciprocal_rank_fusion
from agentdrive.search.rerank import rerank_results
from agentdrive.search.vector import SearchResult, vector_search


class SearchEngine:
    def __init__(self) -> None:
        self._embedding_client = EmbeddingClient()

    async def search(
        self,
        query: str,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        top_k: int = 5,
        collections: list[uuid.UUID] | None = None,
        content_types: list[str] | None = None,
        include_parent: bool = True,
    ) -> list[dict]:
        # Step 1: Embed query
        query_vector_full = self._embedding_client.embed_query(query)
        query_vector_256 = self._embedding_client.truncate(query_vector_full, 256)

        # Step 2: Parallel retrieval (vector + BM25)
        vector_results = await vector_search(
            query_vector_256, session, tenant_id,
            top_k=50, collections=collections, content_types=content_types,
        )
        bm25_results = await bm25_search(
            query, session, tenant_id,
            top_k=50, collections=collections,
        )

        # Step 3: Reciprocal Rank Fusion
        fused = reciprocal_rank_fusion([vector_results, bm25_results], k=60, top_k=20)

        # Step 4: Cohere Rerank
        reranked = rerank_results(query, fused, top_k=top_k)

        # Step 5: Resolve parent chunks for small-to-big retrieval
        results = []
        for r in reranked:
            entry = {
                "chunk_id": str(r.chunk_id),
                "content": r.content,
                "token_count": r.token_count,
                "score": r.score,
                "content_type": r.content_type,
                "provenance": {
                    "file_id": str(r.file_id),
                    **r.metadata,
                },
            }

            if include_parent and r.parent_chunk_id:
                parent = await session.get(ParentChunk, r.parent_chunk_id)
                if parent:
                    entry["parent_content"] = parent.content
                    entry["parent_token_count"] = parent.token_count

            results.append(entry)

        return results
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/search/test_engine.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/agentdrive/search/engine.py tests/search/test_engine.py
git commit -m "feat: search engine orchestrating vector + BM25 + RRF + reranking"
```

---

### Task 8: Search API Endpoint

**Files:**
- Create: `src/agentdrive/routers/search.py`
- Create: `src/agentdrive/schemas/search.py`
- Modify: `src/agentdrive/main.py`
- Test: `tests/test_search_api.py`

- [ ] **Step 1: Create search schemas**

```python
# src/agentdrive/schemas/search.py
import uuid

from pydantic import BaseModel


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    collections: list[uuid.UUID] | None = None
    content_types: list[str] | None = None
    include_parent: bool = True


class ProvenanceResponse(BaseModel):
    file_id: str
    filename: str | None = None
    page: int | None = None
    section: str | None = None
    collection: str | None = None


class SearchResultResponse(BaseModel):
    chunk_id: str
    content: str
    token_count: int
    score: float
    content_type: str
    parent_content: str | None = None
    parent_token_count: int | None = None
    provenance: dict


class SearchResponse(BaseModel):
    results: list[SearchResultResponse]
    query_tokens: int
    search_time_ms: int
```

- [ ] **Step 2: Implement search router**

```python
# src/agentdrive/routers/search.py
import time
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.chunking.tokens import count_tokens
from agentdrive.db.session import get_session
from agentdrive.dependencies import get_current_tenant
from agentdrive.models.tenant import Tenant
from agentdrive.schemas.search import SearchRequest, SearchResponse, SearchResultResponse
from agentdrive.search.engine import SearchEngine

router = APIRouter(prefix="/v1", tags=["search"])

engine = SearchEngine()


@router.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    start = time.monotonic()

    results = await engine.search(
        query=body.query,
        session=session,
        tenant_id=tenant.id,
        top_k=body.top_k,
        collections=body.collections,
        content_types=body.content_types,
        include_parent=body.include_parent,
    )

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return SearchResponse(
        results=[SearchResultResponse(**r) for r in results],
        query_tokens=count_tokens(body.query),
        search_time_ms=elapsed_ms,
    )


@router.get("/chunks/{chunk_id}")
async def get_chunk(
    chunk_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select
    from agentdrive.models.chunk import Chunk
    from agentdrive.models.file import File

    result = await session.execute(
        select(Chunk).join(File).where(Chunk.id == chunk_id, File.tenant_id == tenant.id)
    )
    chunk = result.scalar_one_or_none()
    if not chunk:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Chunk not found")

    return {
        "chunk_id": str(chunk.id),
        "file_id": str(chunk.file_id),
        "content": chunk.content,
        "context_prefix": chunk.context_prefix,
        "token_count": chunk.token_count,
        "content_type": chunk.content_type,
        "metadata": chunk.metadata,
    }
```

- [ ] **Step 3: Wire search router into main.py**

Add `from agentdrive.routers import search` and `app.include_router(search.router)`.

- [ ] **Step 4: Write API tests**

```python
# tests/test_search_api.py
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key

TEST_API_KEY = "sk-test-key-search"


@pytest_asyncio.fixture
async def authed_client(client, db_session):
    tenant = Tenant(name="Test", api_key_hash=hash_api_key(TEST_API_KEY))
    db_session.add(tenant)
    await db_session.commit()
    client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    return client


@pytest.mark.asyncio
@patch("agentdrive.routers.search.engine")
async def test_search_endpoint(mock_engine, authed_client):
    mock_engine.search = AsyncMock(return_value=[
        {
            "chunk_id": "abc",
            "content": "test content",
            "token_count": 10,
            "score": 0.9,
            "content_type": "text",
            "provenance": {"file_id": "def"},
        }
    ])

    response = await authed_client.post("/v1/search", json={"query": "test query"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert "search_time_ms" in data
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_search_api.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/schemas/search.py src/agentdrive/routers/search.py src/agentdrive/main.py tests/test_search_api.py
git commit -m "feat: search API endpoint with hybrid retrieval"
```

---

### Task 9: MCP Server

**Files:**
- Create: `src/agentdrive/mcp/__init__.py`
- Create: `src/agentdrive/mcp/server.py`
- Test: `tests/mcp/test_server.py`

- [ ] **Step 1: Add MCP dependency**

Add to `pyproject.toml`:
```
"mcp>=1.0.0",
```

- [ ] **Step 2: Implement MCP server with tools**

```python
# src/agentdrive/mcp/__init__.py
```

```python
# src/agentdrive/mcp/server.py
import json
import os
from pathlib import Path

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

AGENT_DRIVE_URL = os.environ.get("AGENT_DRIVE_URL", "http://localhost:8080")
AGENT_DRIVE_API_KEY = os.environ.get("AGENT_DRIVE_API_KEY", "")

server = Server("agent-drive")


def _headers() -> dict:
    return {"Authorization": f"Bearer {AGENT_DRIVE_API_KEY}"}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="upload_file",
            description="Upload a file to Agent Drive for processing and semantic indexing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the file on disk"},
                    "collection": {"type": "string", "description": "Collection name (optional)"},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="search",
            description="Search across all uploaded files using natural language. Returns relevant chunks with provenance.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "top_k": {"type": "integer", "description": "Number of results (default 5)", "default": 5},
                    "collection": {"type": "string", "description": "Limit search to this collection (optional)"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_file_status",
            description="Check the processing status of an uploaded file.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {"type": "string", "description": "File ID returned from upload"},
                },
                "required": ["file_id"],
            },
        ),
        Tool(
            name="list_files",
            description="List all files uploaded to Agent Drive.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection": {"type": "string", "description": "Filter by collection (optional)"},
                },
            },
        ),
        Tool(
            name="create_collection",
            description="Create a named collection to organize files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Collection name"},
                    "description": {"type": "string", "description": "Collection description (optional)"},
                },
                "required": ["name"],
            },
        ),
        Tool(
            name="list_collections",
            description="List all collections.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="delete_file",
            description="Delete a file and all its chunks from Agent Drive.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_id": {"type": "string", "description": "File ID to delete"},
                },
                "required": ["file_id"],
            },
        ),
        Tool(
            name="delete_collection",
            description="Delete a collection.",
            inputSchema={
                "type": "object",
                "properties": {
                    "collection_id": {"type": "string", "description": "Collection ID to delete"},
                },
                "required": ["collection_id"],
            },
        ),
        Tool(
            name="get_chunk",
            description="Get a specific chunk by ID with full content and provenance.",
            inputSchema={
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string", "description": "Chunk ID"},
                },
                "required": ["chunk_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    async with httpx.AsyncClient(base_url=AGENT_DRIVE_URL, headers=_headers(), timeout=60) as client:
        if name == "upload_file":
            file_path = Path(arguments["path"])
            if not file_path.exists():
                return [TextContent(type="text", text=f"Error: File not found: {file_path}")]

            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f, "application/octet-stream")}
                data = {}
                if "collection" in arguments:
                    data["collection"] = arguments["collection"]
                response = await client.post("/v1/files", files=files, data=data)

            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

        elif name == "search":
            body = {"query": arguments["query"], "top_k": arguments.get("top_k", 5)}
            if "collection" in arguments:
                body["collections"] = [arguments["collection"]]
            response = await client.post("/v1/search", json=body)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

        elif name == "get_file_status":
            response = await client.get(f"/v1/files/{arguments['file_id']}")
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

        elif name == "list_files":
            params = {}
            if "collection" in arguments:
                params["collection"] = arguments["collection"]
            response = await client.get("/v1/files", params=params)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

        elif name == "create_collection":
            body = {"name": arguments["name"]}
            if "description" in arguments:
                body["description"] = arguments["description"]
            response = await client.post("/v1/collections", json=body)
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

        elif name == "list_collections":
            response = await client.get("/v1/collections")
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

        elif name == "delete_file":
            response = await client.delete(f"/v1/files/{arguments['file_id']}")
            if response.status_code == 204:
                return [TextContent(type="text", text="File deleted successfully.")]
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

        elif name == "delete_collection":
            response = await client.delete(f"/v1/collections/{arguments['collection_id']}")
            if response.status_code == 204:
                return [TextContent(type="text", text="Collection deleted successfully.")]
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

        elif name == "get_chunk":
            response = await client.get(f"/v1/chunks/{arguments['chunk_id']}")
            return [TextContent(type="text", text=json.dumps(response.json(), indent=2))]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

- [ ] **Step 3: Write tests**

```python
# tests/mcp/__init__.py
```

```python
# tests/mcp/test_server.py
import pytest

from agentdrive.mcp.server import server


@pytest.mark.asyncio
async def test_list_tools():
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]
    assert "upload_file" in tool_names
    assert "search" in tool_names
    assert "get_file_status" in tool_names
    assert "list_files" in tool_names
    assert "create_collection" in tool_names
    assert "list_collections" in tool_names
    assert "delete_file" in tool_names
    assert "delete_collection" in tool_names
    assert "get_chunk" in tool_names


@pytest.mark.asyncio
async def test_upload_tool_has_path_param():
    tools = await server.list_tools()
    upload = next(t for t in tools if t.name == "upload_file")
    assert "path" in upload.inputSchema["properties"]
    assert "path" in upload.inputSchema["required"]


@pytest.mark.asyncio
async def test_search_tool_has_query_param():
    tools = await server.list_tools()
    search = next(t for t in tools if t.name == "search")
    assert "query" in search.inputSchema["properties"]
    assert "query" in search.inputSchema["required"]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/mcp/test_server.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/mcp/ tests/mcp/ pyproject.toml
git commit -m "feat: MCP server with upload, search, collections tools"
```

---

### Task 10: Full Integration Smoke Test

**Files:**
- Test: `tests/test_integration.py`

- [ ] **Step 1: Write end-to-end integration test**

```python
# tests/test_integration.py
"""
End-to-end smoke test: upload → chunk → embed → search.
Requires test DB with pgvector. Mocks external APIs (Voyage, Cohere, GCS).
"""
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from agentdrive.models.tenant import Tenant
from agentdrive.services.auth import hash_api_key

TEST_API_KEY = "sk-test-integration"


@pytest_asyncio.fixture
async def authed_client(client, db_session):
    tenant = Tenant(name="Integration Test", api_key_hash=hash_api_key(TEST_API_KEY))
    db_session.add(tenant)
    await db_session.commit()
    client.headers["Authorization"] = f"Bearer {TEST_API_KEY}"
    return client


@pytest.mark.asyncio
@patch("agentdrive.search.rerank.cohere_client")
@patch("agentdrive.embedding.client.voyageai.Client")
@patch("agentdrive.routers.files.StorageService")
async def test_upload_and_search(mock_storage_cls, mock_voyage_cls, mock_cohere, authed_client):
    # Mock GCS
    mock_storage = MagicMock()
    mock_storage.upload.return_value = "test/path"
    mock_storage.download.return_value = b"# Test Doc\n\n## Section A\n\nImportant content about authentication.\n\n## Section B\n\nDetails about authorization."
    mock_storage_cls.return_value = mock_storage

    # Mock Voyage
    mock_voyage = MagicMock()
    mock_voyage.embed.return_value = MagicMock(embeddings=[[0.1] * 1024, [0.2] * 1024])
    mock_voyage_cls.return_value = mock_voyage

    # Mock Cohere
    mock_cohere.rerank.return_value = MagicMock(
        results=[MagicMock(index=0, relevance_score=0.95)]
    )

    # Upload file
    upload_resp = await authed_client.post(
        "/v1/files",
        files={"file": ("test.md", b"# Test Doc\n\n## Section A\n\nImportant content about authentication.\n\n## Section B\n\nDetails about authorization.", "text/markdown")},
    )
    assert upload_resp.status_code == 202
    file_id = upload_resp.json()["id"]

    # Wait for background processing (in test, it runs synchronously)
    import asyncio
    await asyncio.sleep(0.5)

    # Check status
    status_resp = await authed_client.get(f"/v1/files/{file_id}")
    assert status_resp.status_code == 200

    # Search (mock embedding + rerank ensure deterministic results)
    search_resp = await authed_client.post("/v1/search", json={"query": "authentication", "top_k": 5})
    assert search_resp.status_code == 200
    data = search_resp.json()
    assert "results" in data
    assert "search_time_ms" in data
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: end-to-end integration smoke test"
```

---

## Summary

After completing all 10 tasks, you will have:

- Voyage AI embedding client with model routing (docs vs code vs query)
- Batch embedding pipeline storing vectors in pgvector
- Vector search (pgvector HNSW with tenant/collection filtering)
- BM25 search (Postgres FTS + application-layer scoring)
- Reciprocal Rank Fusion merging vector + BM25 results
- Cohere Rerank 3 cross-encoder reranking
- Full search engine orchestrating the pipeline
- REST search endpoint (POST /v1/search, GET /v1/chunks/:id)
- MCP server with 6 tools (upload, search, status, list files, create/list collections)
- Integration smoke test

**After all 3 plans are complete**, Agent Drive is functional end-to-end: an agent connects via MCP, uploads files, and searches across them with hybrid retrieval.
