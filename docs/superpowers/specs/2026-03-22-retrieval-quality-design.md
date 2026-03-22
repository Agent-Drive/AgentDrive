# Retrieval Quality Enhancements — Design Specification

**Date:** 2026-03-22
**Status:** Draft
**Depends on:** Phase 1 (Plans 1-3) complete — 104 tests passing

---

## 1. Overview

Two complementary enhancements to Agent Drive's retrieval quality, both happening at ingest time:

1. **LLM Contextual Enrichment** — Use Claude Haiku to generate a context prefix for every chunk, replacing the current breadcrumb-only approach. Based on Anthropic's Contextual Retrieval research (35-49% fewer retrieval failures).

2. **Table Synthetic Questions** — Generate natural language questions per table chunk so that semantic search can match queries like "what was Q3 revenue?" to tabular data.

Both features use the same underlying pattern: an LLM call at ingest time to enrich chunks before embedding.

---

## 2. LLM Contextual Enrichment

### How It Works

After chunking but before embedding, every chunk is sent to Claude Haiku along with the full document text. Haiku generates a 1-2 sentence context prefix that situates the chunk within the document.

```
Current pipeline:
  File → Chunk → [breadcrumb prefix] → Embed → Store

New pipeline:
  File → Chunk → [Haiku context prefix] → Embed → Store
```

### Prompt

```
<document>
{FULL_DOCUMENT_TEXT}
</document>
Here is the chunk we want to situate within the whole document:
<chunk>
{CHUNK_CONTENT}
</chunk>
Please give a short succinct context to situate this chunk within
the overall document for the purposes of improving search retrieval
of the chunk. Answer only with the succinct context and nothing else.
```

### Prompt Caching

The `<document>` block is identical for all chunks from the same file. With Anthropic's prompt caching:

- First chunk: full price for document tokens (cache write)
- Subsequent chunks: 90% discount on cached document tokens

This reduces cost ~10x. A 100-page document (800 chunks) goes from ~$26 to ~$2-3 with Haiku.

### Context Prefix Replacement

The generated context **replaces** the current breadcrumb in `chunks.context_prefix`. The old breadcrumb (`"File: report.md | Section > Subsection"`) is simple metadata. The new context is richer:

```
Before (breadcrumb):
  "File: board-meeting-q3.md | Board Meeting Minutes > Financial Review"

After (Haiku context):
  "This chunk is from the Q3 2025 board meeting minutes. It covers
   the financial review presented by CFO Mike Johnson, reporting
   $12.4M revenue (34% YoY growth) and $52M ARR."
```

The enriched prefix is what gets prepended to content before embedding, producing dramatically better retrieval.

### Fallback

If the Haiku call fails (rate limit, timeout, API error), fall back to the existing breadcrumb. The chunk still gets embedded — just with lower-quality context. Log the failure for monitoring.

### Cost Model

| Document Size | Chunks | Cost (Haiku + caching) |
|---|---|---|
| 10 pages | ~40 | ~$0.40 |
| 50 pages | ~200 | ~$2.00 |
| 100 pages | ~400 | ~$4.00 |

At projected volume (1,000 documents/month avg 50 pages): ~$2,000/month in enrichment costs.

---

## 3. Table Synthetic Questions

### Problem

Tables embed poorly. A query like "what was Q3 revenue?" is semantically distant from `| Q3 | 4.2 | 12% |` in embedding space. This was the weak spot in testing (Q5 scored 0.07).

### Solution

When a chunk contains a table, generate 5-8 natural language questions that the table can answer. Store these as alias chunks that point back to the original table chunk.

### Prompt

```
Given this table from a document:
{TABLE_CONTENT}

Generate 5-8 natural language questions that someone might ask
that this table could answer. Return only the questions, one per line.
```

### Example

```
Table: | Quarter | Revenue | Growth |
       | Q1 2024 | 3.8B    | 8%     |
       | Q2 2024 | 4.0B    | 10%    |
       | Q3 2024 | 4.2B    | 12%    |

Generated questions:
- What was Q3 2024 revenue?
- How did revenue grow across quarters in 2024?
- Which quarter had the highest growth rate?
- What was the total revenue trend?
- How much did revenue increase from Q1 to Q3?
```

### Storage: chunk_aliases Table

```sql
CREATE TABLE chunk_aliases (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id        uuid NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    file_id         uuid NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    content         text NOT NULL,  -- the synthetic question
    token_count     int NOT NULL,
    embedding       halfvec(256),
    created_at      timestamptz DEFAULT now()
);

CREATE INDEX idx_chunk_aliases_embedding ON chunk_aliases
    USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 128);

CREATE INDEX idx_chunk_aliases_chunk ON chunk_aliases(chunk_id);
CREATE INDEX idx_chunk_aliases_file ON chunk_aliases(file_id);
```

### Search Integration

The search pipeline queries both `chunks` and `chunk_aliases` in the vector search step. When an alias matches, the search returns the **original table chunk** (resolved via `chunk_id`), not the question text.

```
Query: "what was Q3 revenue?"
  → vector search hits alias "What was Q3 2024 revenue?" (score: 0.92)
  → resolve alias.chunk_id → return original table chunk
  → agent gets the actual table data
```

### Table Detection

A chunk is considered a table if its content contains markdown table syntax:
- Contains `|` delimiters on multiple lines
- Contains a separator row (`|---|---|`)

This is a simple heuristic check, not a full parser. Applied after chunking, before enrichment.

---

## 4. Architecture

### New Module: `enrichment/`

```
src/agentdrive/enrichment/
├── __init__.py
├── client.py              # Anthropic client with prompt caching
├── contextual.py          # Context prefix generation per chunk
└── table_questions.py     # Synthetic question generation for tables
```

### enrichment/client.py

Wraps the Anthropic SDK with prompt caching support:

```python
class EnrichmentClient:
    def __init__(self):
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def generate_context(self, document_text: str, chunk_text: str) -> str:
        """Generate context prefix for a chunk using the full document."""
        # Uses prompt caching — document_text is cached across calls
        ...

    def generate_table_questions(self, table_text: str) -> list[str]:
        """Generate synthetic questions for a table chunk."""
        ...
```

### enrichment/contextual.py

Orchestrates enrichment for all chunks from a file:

```python
async def enrich_chunks(
    document_text: str,
    chunk_groups: list[ParentChildChunks],
) -> list[ParentChildChunks]:
    """Enrich all chunks with LLM-generated context prefixes."""
    client = EnrichmentClient()
    for group in chunk_groups:
        for child in group.children:
            context = client.generate_context(document_text, child.content)
            child.context_prefix = context
        # Also enrich parent
        group.parent.context_prefix = client.generate_context(
            document_text, group.parent.content
        )
    return chunk_groups
```

### enrichment/table_questions.py

Detects tables and generates synthetic questions:

```python
def is_table_chunk(content: str) -> bool:
    """Check if chunk contains a markdown table."""
    lines = content.strip().split("\n")
    pipe_lines = [l for l in lines if "|" in l]
    separator_lines = [l for l in lines if re.match(r'\|[\s\-|]+\|', l)]
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
                questions = client.generate_table_questions(child.content)
                for q in questions:
                    aliases.append({"question": q, "chunk": child})
    return aliases
```

### Changes to Ingest Pipeline

`services/ingest.py` adds the enrichment step:

```python
# After chunking, before storing:
document_text = data.decode("utf-8", errors="replace")
chunk_groups = await enrich_chunks(document_text, chunk_groups)
table_aliases = await generate_table_aliases(chunk_groups)

# Store chunks (with enriched context_prefix)
# Store table aliases
# Embed chunks + aliases
```

### Changes to Search

`search/vector.py` queries both tables:

```sql
-- Existing chunk search
SELECT ... FROM chunks c JOIN files f ON ...
UNION ALL
-- New alias search (resolves to parent chunk)
SELECT c.id, c.file_id, c.content, ... , ca.embedding <=> :query AS distance
FROM chunk_aliases ca
JOIN chunks c ON ca.chunk_id = c.id
JOIN files f ON c.file_id = f.id
WHERE ...
ORDER BY distance
LIMIT :top_k
```

---

## 5. Data Model Changes

### New Table: chunk_aliases

```sql
CREATE TABLE chunk_aliases (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id        uuid NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    file_id         uuid NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    content         text NOT NULL,
    token_count     int NOT NULL,
    embedding       halfvec(256),
    created_at      timestamptz DEFAULT now()
);
```

### New Alembic Migration

`alembic/versions/002_chunk_aliases.py` — adds the `chunk_aliases` table with HNSW index.

### Config Change

New env var: `ANTHROPIC_API_KEY` for Haiku calls.

---

## 6. Dependencies

| Dependency | Purpose |
|---|---|
| `anthropic` SDK | Haiku API calls with prompt caching |

---

## 7. What Changes vs What Doesn't

### Changes

| Component | Change |
|---|---|
| `services/ingest.py` | Add enrichment step between chunking and embedding |
| `chunks.context_prefix` | Now contains LLM-generated context (was breadcrumb) |
| `search/vector.py` | Also search chunk_aliases table |
| `pyproject.toml` | Add `anthropic` SDK |
| Database | New `chunk_aliases` table + HNSW index |
| `.env` | New `ANTHROPIC_API_KEY` |

### Doesn't Change

- Chunking logic (same chunkers, same boundaries)
- Embedding logic (same Voyage models, same dimensions)
- BM25 search (still searches chunk content)
- Reranking (still uses Cohere)
- API surface (same endpoints, same response format)
- MCP tools (same interface)

---

## 8. Expected Impact

Based on Anthropic's published research and our testing:

| Metric | Current | Expected |
|---|---|---|
| Retrieval failure rate | Baseline | -35% (contextual) to -49% (contextual + BM25) |
| Table search quality (e.g., Q5) | 0.07 score | 0.5+ score (with synthetic questions) |
| Ingest time | ~3 seconds | ~15-30 seconds (LLM calls) |
| Ingest cost per document | ~$0 | ~$2-4 per 50-page doc |

---

## 9. Scope

### In Scope

- Anthropic client with prompt caching
- Context prefix generation for all chunks via Haiku
- Table detection heuristic
- Synthetic question generation for table chunks
- chunk_aliases table and migration
- Search integration (query aliases alongside chunks)
- Fallback to breadcrumb on LLM failure
- Alembic migration for new table

### Out of Scope

- Pluggable LLM provider (Haiku only for now)
- Re-enrichment of existing chunks (new uploads only)
- UI for monitoring enrichment costs
- Enrichment quality evaluation framework
