# Agent Drive — Design Specification

**Date:** 2026-03-22
**Status:** Draft
**Scope:** Phase 1 — SaaS MVP on GCP

---

## 1. Overview

Agent Drive is an agent-native file intelligence layer that solves the mismatch between how files are stored and how AI agents need to access them. It ingests files — PDFs, documents, spreadsheets, images, code — and immediately processes them into structured, semantically-indexed, chunk-level representations that agents can retrieve with precision.

### Business Model

- **Open-core**: open-source engine, hosted SaaS product
- **Phase 1** (this spec): SaaS on GCP, single-container deployment
- **Phase 2** (future): Open-source with `docker compose up` self-host experience

### Primary Interface

Agents interact with Agent Drive via an **MCP server**. Claude Code (and other MCP-compatible agents) connects to Agent Drive through MCP tools like `upload_file`, `search`, `get_chunk`, `create_collection`.

---

## 2. System Architecture

```
Agent (Claude Code)
     │
     ▼
MCP Server (Agent Drive)
     │
     ▼
┌─────────────────────────────────┐
│        Agent Drive API           │
│        (FastAPI, Cloud Run)      │
│                                  │
│  ┌───────────┐  ┌─────────────┐ │
│  │  Ingest    │  │  Retrieval  │ │
│  │  Pipeline  │  │  Engine     │ │
│  └─────┬─────┘  └──────┬─────┘ │
│        │                │       │
│  ┌─────▼─────┐  ┌──────▼─────┐ │
│  │  Chunker   │  │  Search    │ │
│  │  Registry  │  │  (vector + │ │
│  │            │  │   BM25)    │ │
│  └─────┬─────┘  └──────┬─────┘ │
│        │                │       │
│  ┌─────▼─────┐  ┌──────▼─────┐ │
│  │  Embedding │  │  Reranker  │ │
│  │  Client    │  │  (Cohere)  │ │
│  │  (Voyage)  │  │            │ │
│  └─────┬─────┘  └──────┬─────┘ │
│        └────────┬───────┘       │
│                 ▼               │
│  ┌──────────────────────────┐   │
│  │ Cloud SQL (Postgres +    │   │
│  │ pgvector)                │   │
│  └──────────────────────────┘   │
│  ┌──────────────────────────┐   │
│  │ GCS (raw file storage)   │   │
│  └──────────────────────────┘   │
└─────────────────────────────────┘
```

### Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Language | Python (FastAPI) | Ecosystem for ML/embedding libs, async support |
| Database | Cloud SQL Postgres + pgvector | Managed, pgvector for vectors, single DB |
| File storage | GCS | Managed, GCP-native, cheap |
| Embedding (docs) | Voyage 4 ($0.06/M tokens) | Best quality, shared embedding space |
| Embedding (code) | voyage-code-3 ($0.18/M tokens) | Best code retrieval, separate space |
| Query embedding | voyage-4-lite ($0.02/M tokens) | Same space as voyage-4, cheapest |
| Reranker | Cohere Rerank 3 ($1/1K queries) | +10-25% nDCG, trivial API integration |
| PDF parsing | Docling v2 (MIT license) | Best OSS structure extraction, tables |
| OCR fallback | Google Document AI | Best scanned doc quality, GCP-native |
| Deployment | Cloud Run (single container) | Auto-scale, managed, stateless |
| Auth | API keys (Phase 1) | Simple, stateless, OAuth2 in Phase 2 |

### Deployment Topology

**SaaS (Phase 1):**
- 1 Cloud Run service (Agent Drive API)
- Cloud SQL (managed Postgres + pgvector)
- GCS bucket (raw file storage)
- External APIs: Voyage, Cohere

**Self-host (Phase 2, future):**
- Same Docker image, different config
- Local Postgres + pgvector container
- Local disk for file storage
- Nomic Embed v1.5 via FastEmbed (in-process, no API)
- voyage-4-nano (open-weight) as alternative

---

## 3. Data Model

```sql
-- Tenants (API key holders)
CREATE TABLE tenants (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL,
    api_key_hash    text NOT NULL,
    created_at      timestamptz DEFAULT now(),
    settings        jsonb DEFAULT '{}'
);

-- Collections (scoped groups of files)
CREATE TABLE collections (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id),
    name            text NOT NULL,
    description     text,
    created_at      timestamptz DEFAULT now(),
    UNIQUE(tenant_id, name)
);

-- Files (raw uploads, stored in GCS)
CREATE TABLE files (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id),
    collection_id   uuid REFERENCES collections(id),  -- nullable
    filename        text NOT NULL,
    content_type    text NOT NULL,  -- pdf, code, markdown, json, image, etc.
    gcs_path        text NOT NULL,
    file_size       bigint NOT NULL,
    status          text NOT NULL DEFAULT 'pending',
        -- pending → processing → ready → failed
    metadata        jsonb DEFAULT '{}',
    created_at      timestamptz DEFAULT now()
);

-- Chunks (processed pieces of files)
CREATE TABLE chunks (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id         uuid NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    chunk_index     int NOT NULL,
    content         text NOT NULL,
    context_prefix  text NOT NULL DEFAULT '',
    token_count     int NOT NULL,
    content_type    text NOT NULL,  -- code, text, image, table
    embedding       halfvec(256) NOT NULL,   -- MRL-truncated for HNSW
    embedding_full  halfvec(1024),           -- full Voyage dims for re-rank
    metadata        jsonb DEFAULT '{}',
        -- line numbers, function name, heading breadcrumb, page number, etc.
    created_at      timestamptz DEFAULT now()
);

-- Parent chunks (for small-to-big retrieval)
CREATE TABLE parent_chunks (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id         uuid NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    content         text NOT NULL,
    token_count     int NOT NULL,
    metadata        jsonb DEFAULT '{}',
    created_at      timestamptz DEFAULT now()
);

-- Child-to-parent mapping
ALTER TABLE chunks ADD COLUMN parent_chunk_id uuid REFERENCES parent_chunks(id);

-- Indexes
-- HNSW for non-code chunks (voyage-4 space)
CREATE INDEX idx_chunks_embedding_docs ON chunks
    USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 128)
    WHERE content_type != 'code';

-- HNSW for code chunks (voyage-code-3 space)
CREATE INDEX idx_chunks_embedding_code ON chunks
    USING hnsw (embedding halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 128)
    WHERE content_type = 'code';

CREATE INDEX idx_chunks_file ON chunks(file_id);
CREATE INDEX idx_chunks_content_fts ON chunks
    USING gin (to_tsvector('english', content));

CREATE INDEX idx_files_tenant ON files(tenant_id);
CREATE INDEX idx_files_collection ON files(collection_id);
CREATE INDEX idx_collections_tenant ON collections(tenant_id);
```

### Key Design Decisions

- `collection_id` is nullable — files can exist outside any collection
- `status` tracks ingest pipeline: pending → processing → ready → failed
- `context_prefix` stored separately so we can re-embed without re-chunking
- Two embedding columns: `halfvec(256)` for fast HNSW, `halfvec(1024)` for re-ranking
- `parent_chunks` table enables small-to-big retrieval pattern
- GIN index on `content` for Postgres native full-text search (BM25 approximation)
- Code chunks use the same `chunks` table with `content_type = 'code'`. They get a **separate filtered HNSW index** (partial index on `content_type = 'code'`). Search queries both indexes and merges via RRF.

---

## 4. Ingest Pipeline

```
File Upload
     │
     ▼
Type Detection (MIME + extension + content sniffing)
     │
     ├──► PDF         → Docling v2 (structure extraction)
     │                   → Google Doc AI fallback (scanned PDFs)
     │
     ├──► Markdown    → Custom heading-based parser
     │
     ├──► Code        → tree-sitter AST parser
     │
     ├──► JSON/YAML   → Key-path subtree parser
     │
     ├──► CSV/XLSX    → Row-group + header parser
     │
     ├──► Notebook    → Cell-pair grouping parser
     │
     ├──► Image       → OCR text extraction (basic, no multi-modal search)
     │
     └──► Plain text  → Paragraph-based parser
              │
              ▼
     Parent-Child Hierarchy
     (create parent chunks ~1500 tokens,
      child chunks ~300 tokens)
              │
              ▼
     Context Prepending
     (breadcrumb + metadata prefix per chunk)
              │
              ▼
     Embedding (Voyage 4 / voyage-code-3)
              │
              ▼
     Store in pgvector + FTS index
              │
              ▼
     Mark file status = 'ready'
```

### 4.1 File Processing is Async

Upload returns immediately with file ID and `status: pending`. Processing happens in a background asyncio task within the same process (Phase 1). The agent can poll `get_file_status` to check progress.

**Max upload size:** 32MB (Cloud Run default). Documents larger than this are rejected with 413. Streaming/resumable uploads are Phase 2.

**Scale path:** If asyncio background tasks become a bottleneck (many concurrent uploads), migrate to Cloud Tasks or Pub/Sub for decoupled worker processing.

---

## 5. Document Chunking Engine

This is the core differentiator. Every file type gets a purpose-built chunker that understands its structure.

### 5.1 Design Principles

1. **Semantic boundaries over fixed-size** — never split mid-sentence, mid-function, mid-table
2. **Parent-child (small-to-big)** — embed small children (~300 tokens), return parent (~1500 tokens) to agent
3. **Context prepending** — every chunk gets a breadcrumb/metadata prefix before embedding
4. **Atomic elements** — lists, code blocks, tables are never split across chunks
5. **10-15% sentence-aligned overlap** between adjacent chunks
6. **Merge tiny chunks** — sections < 100 tokens merge upward into previous sibling

### 5.2 Evidence Base

| Technique | Evidence | Impact |
|-----------|----------|--------|
| Parent-child retrieval | LlamaIndex benchmarks, production use at Notion/Glean/Cohere | +15-20% relevance |
| Context prepending (breadcrumbs) | Anthropic contextual retrieval (Sep 2024), community replications | +20-35% retrieval accuracy on docs |
| Hybrid vector + BM25 | BEIR benchmark (NeurIPS 2021, arXiv:2104.08663), 18 datasets | +2-8 nDCG@10 |
| Reranking (Cohere Rerank 3) | BEIR benchmarks, production consensus | +10-25% nDCG@10 |
| AST code chunking | CodeSearchNet (arXiv:1909.09436), industry convergence | +15-25% recall |
| 512 tokens sweet spot | Pinecone evals, embedding model training distributions | Consensus |
| Sentence-aligned 10-15% overlap | Practitioner benchmarks, LangChain evaluations | +3-5% nDCG |

### 5.3 PDF Chunker

**Parser:** Docling v2 (MIT license, best OSS table extraction)
**OCR fallback:** Google Document AI (for scanned PDFs)

```
PDF → Docling → DoclingDocument (hierarchical tree)
                     │
                     ├── Section headings → chunk boundaries
                     ├── Paragraphs → merge up to ~300 tokens (child), ~1500 tokens (parent)
                     ├── Tables → atomic chunks, dual serialization:
                     │            - NL summary for embedding (retrieval)
                     │            - Markdown for LLM (reasoning)
                     │            - Synthetic questions generated at ingest
                     ├── Figures → caption text extracted
                     └── Code blocks → routed to code chunker
```

**Heading hierarchy reconstruction:**
- Docling's DocLayNet model detects heading regions
- Font-size heuristics assign heading levels (H1/H2/H3)
- Numbering patterns (1., 1.1, 1.1.1) as additional signal
- Breadcrumb: `"Document Title > Section > Subsection"`

**Table handling (critical):**
- Tables extracted via Docling's TableFormer model
- Small tables (< 512 tokens): single atomic chunk
- Large tables: split by rows, header repeated in each chunk
- Each table chunk gets:
  - NL summary prepended for embedding
  - 5-10 synthetic questions generated via LLM (Phase 2)
  - Full markdown stored for LLM reasoning

### 5.4 Markdown Chunker

```
Markdown → Parse AST (heading tree)
              │
              ├── Extract front matter → propagate as metadata to all chunks
              ├── Split at H1+H2 (primary boundaries)
              ├── If chunk > max_size → split at H3
              ├── If still > max_size → split at paragraph boundaries
              ├── Code blocks → atomic, keep preceding paragraph attached
              ├── Tables → atomic, never split
              ├── Tiny sections (< 100 tokens) → merge upward
              └── Links → strip URLs for embedding, store originals
```

**Breadcrumb:** `"API Reference > Authentication > OAuth2"` prepended to every chunk for embedding.

**Code blocks inside markdown:** Protected as atomic units. The paragraph immediately preceding a code block stays attached.

### 5.5 Code Chunker

**Parser:** tree-sitter (supports all languages Claude Code works with)

```
Source file → tree-sitter AST
                  │
                  ├── Functions/methods → individual chunks
                  ├── Classes → signature + docstring prepended to each method chunk
                  ├── Import block → separate chunk
                  ├── Function > 512 tokens → split at nested blocks
                  ├── Function < 64 tokens → merge with adjacent
                  └── Top-level statements → grouped into chunks
```

**Context prefix:** `"File: src/auth/service.py | Class: AuthService | Method: authenticate"`

**Embedding:** Code files use `voyage-code-3` (separate vector space from document embeddings). Retrieval merges results via Reciprocal Rank Fusion.

### 5.6 Structured Data Chunker (JSON/YAML/TOML)

```
Config → Parse into tree
           │
           ├── Top-level keys → individual chunks
           ├── Subtree > 512 tokens → recurse to next level
           ├── Subtree < 64 tokens → merge with siblings
           └── Arrays of objects → each object is a chunk
```

**Context prefix:** `"file: config.yaml | path: api.endpoints[0]"`

### 5.7 Spreadsheet Chunker (CSV/XLSX)

```
Spreadsheet → Detect headers (first row)
                │
                ├── Group rows (~30-50 per chunk, stay under 512 tokens)
                ├── Column headers prepended to every chunk
                ├── If "category" column exists → group by category
                └── Serialize to markdown table format
```

**Context prefix:** `"File: q3_metrics.xlsx | Sheet: Revenue | Columns: Region, Revenue, Growth"`

### 5.8 Notebook Chunker (.ipynb)

```
Notebook → Iterate cells
             │
             ├── Markdown cell + following code cell → paired chunk
             ├── Large code cells (> 512 tokens) → route to code chunker
             ├── Include text outputs, skip binary/image outputs
             └── Standalone code cells → individual chunks
```

**Context prefix:** `"Notebook: analysis.ipynb | Section: Data Loading | Cell: 3"`

### 5.9 Context Prepending (All Chunkers)

Every chunk gets metadata prepended before embedding. This is the single highest-ROI intervention.

| File Type | Context Prefix |
|-----------|---------------|
| PDF | `doc_title + " > " + section_heading` |
| Markdown | heading breadcrumb (`H1 > H2 > H3`) |
| Code | `file_path + class_name + function_signature` |
| JSON/YAML | `file_path + key_path` |
| Spreadsheet | `file_name + sheet_name + column_headers` |
| Notebook | `notebook_title + section_heading + cell_number` |

**Evidence:** Anthropic's contextual retrieval research (Sep 2024) showed context prepending reduces retrieval failures by 35%. Combined with BM25: 49%. Combined with BM25 + reranking: 67%.

---

## 6. Retrieval Engine

### 6.1 Query Pipeline

```
Agent query: "how does token refresh work"
                │
                ▼
        Query embedding (voyage-4-lite, $0.02/M)
                │
        ┌───────┴───────┐
        ▼               ▼
  Vector Search     Full-Text Search
  (pgvector HNSW)   (Postgres tsvector/GIN)
  Top 50            Top 50
        │               │
        └───────┬───────┘
                ▼
   Reciprocal Rank Fusion (RRF)
        Top 20 candidates
                │
                ▼
   Re-rank with full 1024d vectors
   (cosine similarity on embedding_full)
        Top 10
                │
                ▼
   Cohere Rerank 3 (cross-encoder)
        Final top K
                │
                ▼
   Map children → parents (small-to-big)
   Deduplicate parents
                │
                ▼
   Return to agent with:
   - chunk content (parent context)
   - token count
   - provenance (file, page, section)
   - relevance score
```

### 6.2 Hybrid Search: Vector + BM25

Cloud SQL does not support ParadeDB (pg_search), so we use:

1. **pgvector HNSW** on `halfvec(256)` for semantic search
2. **Postgres native FTS** (tsvector/tsquery with GIN index) for keyword candidate retrieval
3. **Application-layer BM25 re-ranking** in Python for proper term frequency saturation and document length normalization

**Reciprocal Rank Fusion (RRF):** Merges vector and BM25 result lists with k=60.

**Evidence:** BEIR benchmark (arXiv:2104.08663) — hybrid search improves nDCG@10 by +2-8 across 18 datasets. Weaviate testing: +5-15% precision.

**Scale path:** If BM25 quality or performance becomes insufficient, add Elasticsearch sidecar on Cloud Run.

### 6.3 Reranking

**Phase 1:** Cohere Rerank 3 via API.
- Rerank top 20 candidates after hybrid fusion
- +10-25% nDCG@10 (BEIR benchmarks)
- ~150-300ms added latency (acceptable for doc retrieval)
- ~$300/month at 10K queries/day

**Phase 2:** Evaluate self-hosted `bge-reranker-v2-large` if volume justifies GPU.

### 6.4 Search Scoping

```
Search all:       POST /search { query: "auth flow" }
Search scoped:    POST /search { query: "auth flow", collection: "project-alpha" }
Search multiple:  POST /search { query: "auth flow", collections: ["alpha", "beta"] }
```

### 6.5 Token-Aware Responses

Every result includes token count. The agent decides what fits in its context window:

```json
{
  "results": [
    {
      "chunk_id": "...",
      "content": "...",
      "token_count": 342,
      "score": 0.87,
      "provenance": {
        "file": "auth-spec.pdf",
        "page": 12,
        "section": "Authentication > OAuth2 > Token Refresh",
        "collection": "project-alpha"
      }
    }
  ]
}
```

---

## 7. MCP Server Interface

The MCP server exposes these tools to agents:

### File Operations

| Tool | Description |
|------|-------------|
| `upload_file` | Upload a file to Agent Drive. Returns file ID. Processing is async. |
| `get_file_status` | Check if a file has been processed (pending/processing/ready/failed) |
| `list_files` | List files, optionally filtered by collection |
| `delete_file` | Delete a file and all its chunks |

### Collection Operations

| Tool | Description |
|------|-------------|
| `create_collection` | Create a named collection |
| `list_collections` | List all collections |
| `delete_collection` | Delete a collection (files optionally deleted or orphaned) |

### Search Operations

| Tool | Description |
|------|-------------|
| `search` | Semantic + keyword hybrid search. Params: query, top_k, collections (optional), content_type filter (optional) |
| `get_chunk` | Get a specific chunk by ID with full content and provenance |
| `get_file_chunks` | Get all chunks for a file (for full-file retrieval) |

### Example Agent Interaction

```
Agent: upload_file("quarterly-report.pdf", collection="q3-financials")
→ { file_id: "abc-123", status: "processing" }

Agent: get_file_status("abc-123")
→ { status: "ready", chunks: 47, token_count: 18420 }

Agent: search("what was Q3 revenue growth?", collections=["q3-financials"])
→ [{ content: "Revenue grew 12% YoY to $4.2B...", token_count: 342, score: 0.91, ... }]
```

---

## 8. Embedding Strategy

### Model Selection

| Content Type | Model | Dims | Price | Space |
|---|---|---|---|---|
| Documents, markdown, configs | voyage-4 | 1024 | $0.06/M tokens | voyage-4 shared |
| Code files | voyage-code-3 | 1024 | $0.18/M tokens | Separate space |
| Query-time embedding | voyage-4-lite | 1024 | $0.02/M tokens | voyage-4 shared |

**Shared embedding space:** voyage-4 and voyage-4-lite share the same space. We can embed documents with the expensive model and queries with the cheap model. Zero quality loss.

**Code is separate:** voyage-code-3 uses a different embedding space. Code chunks get their own HNSW index. Search merges results via RRF.

### Vector Storage

- `halfvec(256)`: MRL-truncated, HNSW-indexed for fast search (~4ms at 500K vectors)
- `halfvec(1024)`: Full dimensions, stored for re-ranking (no HNSW index)
- Storage: ~520 bytes/vector (256d) + ~2KB/vector (1024d) = ~2.5KB per chunk
- 1M chunks fits comfortably in 8GB RAM

### Pluggable Interface

All embedding calls go through an `EmbeddingClient` interface that speaks OpenAI's `/v1/embeddings` API format. Swapping providers is a config change:

```yaml
embedding:
  provider: "voyage"
  model: "voyage-4"
  api_key: "${VOYAGE_API_KEY}"
  dimensions: 256  # MRL truncation
```

---

## 9. Authentication

**Phase 1: API keys only.**

- Each tenant gets one or more API keys
- Keys are hashed (bcrypt) and stored in the `tenants` table
- Keys are passed via `Authorization: Bearer <key>` header
- MCP server stores the key in its config

**Phase 2 (future):** OAuth2 / JWT for user-level permissions within a tenant.

---

## 10. API Design

### REST Endpoints

```
POST   /v1/files                    Upload a file
GET    /v1/files/:id                Get file status and metadata
GET    /v1/files                    List files (filterable)
DELETE /v1/files/:id                Delete a file

POST   /v1/collections              Create a collection
GET    /v1/collections              List collections
DELETE /v1/collections/:id          Delete a collection

POST   /v1/search                   Hybrid search
GET    /v1/chunks/:id               Get a specific chunk
GET    /v1/files/:id/chunks         Get all chunks for a file
```

### File Upload

```
POST /v1/files
Content-Type: multipart/form-data

file: <binary>
collection: "project-alpha"  (optional)
metadata: {"source": "email", "date": "2026-03-01"}  (optional)

→ 202 Accepted
{
  "id": "abc-123",
  "status": "pending",
  "filename": "quarterly-report.pdf"
}
```

### Search

```
POST /v1/search
{
  "query": "what was Q3 revenue growth?",
  "top_k": 5,
  "collections": ["q3-financials"],
  "content_types": ["text", "table"],
  "include_parent": true
}

→ 200 OK
{
  "results": [
    {
      "chunk_id": "...",
      "content": "...",
      "parent_content": "...",  // larger context if include_parent=true
      "token_count": 342,
      "parent_token_count": 1420,
      "score": 0.91,
      "provenance": {
        "file_id": "...",
        "filename": "quarterly-report.pdf",
        "page": 12,
        "section": "Financial Results > Revenue",
        "collection": "q3-financials"
      }
    }
  ],
  "query_tokens": 8,
  "search_time_ms": 127
}
```

---

## 11. GCP Infrastructure

```
┌─────────────────────────────────────────────────┐
│                    GCP Project                    │
│                                                   │
│  Cloud Run                                        │
│  ├── agent-drive-api (single container)           │
│  │   min instances: 1 (avoid cold starts)         │
│  │   max instances: 10 (auto-scale)               │
│  │   memory: 2Gi                                  │
│  │   cpu: 2                                       │
│  │                                                │
│  Cloud SQL (Postgres 16 + pgvector)               │
│  ├── db-f1-micro → db-custom-2-8192 as needed     │
│  │   pgvector extension enabled                   │
│  │                                                │
│  GCS                                              │
│  ├── agent-drive-files bucket                     │
│  │   lifecycle: none (keep files indefinitely)    │
│  │                                                │
│  External APIs                                    │
│  ├── Voyage AI (embedding)                        │
│  ├── Cohere (reranking)                           │
│  └── Google Document AI (OCR fallback)            │
└─────────────────────────────────────────────────┘
```

### Cost Estimate (Early Stage, <1K users)

| Component | Monthly Cost |
|-----------|-------------|
| Cloud Run (1 min instance, auto-scale) | ~$30-80 |
| Cloud SQL (db-f1-micro) | ~$10-30 |
| GCS (storage) | ~$5-10 |
| Voyage embedding | ~$50-200 |
| Cohere reranking | ~$100-300 |
| Google Doc AI (OCR, occasional) | ~$10-30 |
| **Total** | **~$200-650/month** |

---

## 12. Evaluation Strategy

### How We Measure Chunking Quality

**Layer 1 — Intrinsic (no queries needed):**
- Chunk coherence: embedding variance within chunk (lower = more coherent)
- Boundary quality: embedding discontinuity at chunk boundaries
- Size distribution: coefficient of variation, % hitting min/max limits
- Self-containedness: LLM judge scores (1-5)

**Layer 2 — Retrieval (needs queries):**
- nDCG@10, MRR, Hit Rate, MAP
- Context Precision / Recall (RAGAS framework)
- A/B comparison vs fixed-size baseline

**Layer 3 — End-to-end:**
- Faithfulness and answer relevancy (RAGAS)
- Human evaluation on 50-100 query sample

**Benchmark datasets:** BEIR subsets, Natural Questions, HotpotQA, plus our own domain-specific test corpus.

---

## 13. Phase 1 Scope

### In Scope

- Single-container FastAPI service on Cloud Run
- File upload, processing, and retrieval via REST API
- MCP server for Claude Code integration
- PDF, markdown, code, JSON/YAML, CSV/XLSX, notebook, plain text support
- Parent-child chunking with context prepending
- Hybrid search (vector + Postgres FTS + application-layer BM25)
- Cohere Rerank 3 integration
- Voyage 4 + voyage-code-3 embedding
- API key authentication
- Collections for file organization

### Out of Scope (Phase 2+)

- Web dashboard / UI
- OAuth2 / user-level permissions
- Self-host packaging (docker-compose)
- LLM-based contextual retrieval (Tier 3 context generation)
- Late chunking (requires Jina model support)
- Synthetic question generation for tables
- Image captioning / multi-modal semantic search (basic OCR text extraction IS in scope)
- Real-time file sync (watch directories)
- Webhook notifications for processing completion
- Usage metering / billing

---

## 14. Open Questions

1. **BM25 scaling:** Application-layer BM25 works at <500K documents. When do we add Elasticsearch?
2. **Embedding dimension:** Start with 256d MRL or go straight to 512d for better quality?
3. **Rate limiting:** Per-tenant rate limits on search and upload?
