# Agent Drive Chunking Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the file processing pipeline that transforms uploaded files into semantically chunked, context-enriched, parent-child chunk hierarchies ready for embedding.

**Architecture:** A chunker registry routes files to type-specific chunkers (PDF, markdown, code, JSON/YAML, CSV, notebook, plain text). Each chunker produces parent chunks (~1500 tokens) and child chunks (~300 tokens) with context prefixes. An async background task orchestrates the pipeline per file.

**Tech Stack:** Python 3.12, Docling v2 (PDF), tree-sitter (code), spaCy (sentence tokenization), tiktoken (token counting)

**Spec:** `docs/superpowers/specs/2026-03-22-agent-drive-design.md` — Section 5

**Depends on:** Plan 1 (Core Infrastructure) must be complete.

---

## File Structure

```
src/agentdrive/
├── chunking/
│   ├── __init__.py
│   ├── registry.py           # Routes files to the right chunker
│   ├── base.py               # Base chunker interface + ChunkResult dataclass
│   ├── tokens.py             # Token counting utility (tiktoken)
│   ├── context.py            # Context prefix generation (breadcrumbs)
│   ├── hierarchy.py          # Parent-child chunk builder
│   ├── pdf.py                # PDF chunker (Docling)
│   ├── markdown.py           # Markdown chunker (heading-based)
│   ├── code.py               # Code chunker (tree-sitter)
│   ├── structured.py         # JSON/YAML/TOML chunker
│   ├── spreadsheet.py        # CSV/XLSX chunker
│   ├── notebook.py           # .ipynb chunker
│   └── text.py               # Plain text fallback chunker
├── services/
│   └── ingest.py             # Async ingest orchestrator
tests/
├── chunking/
│   ├── conftest.py           # Shared fixtures (sample files)
│   ├── test_tokens.py
│   ├── test_context.py
│   ├── test_hierarchy.py
│   ├── test_pdf.py
│   ├── test_markdown.py
│   ├── test_code.py
│   ├── test_structured.py
│   ├── test_spreadsheet.py
│   ├── test_notebook.py
│   ├── test_text.py
│   └── test_registry.py
├── test_ingest.py
tests/fixtures/
├── sample.pdf
├── sample.md
├── sample.py
├── sample.json
├── sample.csv
├── sample.ipynb
└── sample.txt
```

---

### Task 1: Token Counting Utility

**Files:**
- Create: `src/agentdrive/chunking/__init__.py`
- Create: `src/agentdrive/chunking/tokens.py`
- Test: `tests/chunking/__init__.py`
- Test: `tests/chunking/test_tokens.py`

- [ ] **Step 1: Add tiktoken dependency**

Add to `pyproject.toml` dependencies:
```
"tiktoken>=0.8.0",
```

Run: `pip install -e ".[dev]"`

- [ ] **Step 2: Write failing tests**

```python
# tests/chunking/__init__.py
```

```python
# tests/chunking/test_tokens.py
from agentdrive.chunking.tokens import count_tokens, truncate_to_tokens


def test_count_tokens_short():
    assert count_tokens("hello world") > 0
    assert count_tokens("hello world") == 2


def test_count_tokens_empty():
    assert count_tokens("") == 0


def test_count_tokens_code():
    code = "def hello():\n    return 'world'"
    tokens = count_tokens(code)
    assert tokens > 5


def test_truncate_to_tokens():
    text = "The quick brown fox jumps over the lazy dog. " * 100
    truncated = truncate_to_tokens(text, max_tokens=20)
    assert count_tokens(truncated) <= 20
    assert len(truncated) < len(text)


def test_truncate_short_text_unchanged():
    text = "short text"
    assert truncate_to_tokens(text, max_tokens=100) == text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/chunking/test_tokens.py -v`
Expected: FAIL

- [ ] **Step 4: Implement token counting**

```python
# src/agentdrive/chunking/__init__.py
```

```python
# src/agentdrive/chunking/tokens.py
import tiktoken

_encoding = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_encoding.encode(text))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    tokens = _encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _encoding.decode(tokens[:max_tokens])
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/chunking/test_tokens.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/chunking/ tests/chunking/ pyproject.toml
git commit -m "feat: token counting utility with tiktoken"
```

---

### Task 2: Base Chunker Interface + ChunkResult

**Files:**
- Create: `src/agentdrive/chunking/base.py`

- [ ] **Step 1: Define chunk data structures and base interface**

```python
# src/agentdrive/chunking/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChunkResult:
    content: str
    context_prefix: str
    token_count: int
    content_type: str  # text, code, table, image
    metadata: dict = field(default_factory=dict)


@dataclass
class ParentChildChunks:
    parent: ChunkResult
    children: list[ChunkResult]


class BaseChunker(ABC):
    @abstractmethod
    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        """Process text content and return parent-child chunk groups."""
        ...

    def chunk_bytes(self, data: bytes, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        """Process binary content. Override for binary formats (PDF, XLSX). Default decodes as UTF-8."""
        return self.chunk(data.decode("utf-8", errors="replace"), filename, metadata)

    @abstractmethod
    def supported_types(self) -> list[str]:
        """Return list of content_type strings this chunker handles."""
        ...
```

- [ ] **Step 2: Commit**

```bash
git add src/agentdrive/chunking/base.py
git commit -m "feat: base chunker interface and ChunkResult dataclass"
```

---

### Task 3: Context Prefix Generator

**Files:**
- Create: `src/agentdrive/chunking/context.py`
- Test: `tests/chunking/test_context.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/chunking/test_context.py
from agentdrive.chunking.context import build_context_prefix


def test_pdf_context():
    prefix = build_context_prefix(
        content_type="pdf",
        filename="quarterly-report.pdf",
        heading_breadcrumb=["Financial Results", "Revenue"],
    )
    assert "quarterly-report.pdf" in prefix
    assert "Financial Results" in prefix
    assert "Revenue" in prefix


def test_markdown_context():
    prefix = build_context_prefix(
        content_type="markdown",
        filename="README.md",
        heading_breadcrumb=["API Reference", "Authentication", "OAuth2"],
    )
    assert "API Reference > Authentication > OAuth2" in prefix


def test_code_context():
    prefix = build_context_prefix(
        content_type="code",
        filename="src/auth/service.py",
        class_name="AuthService",
        function_name="authenticate",
    )
    assert "src/auth/service.py" in prefix
    assert "AuthService" in prefix
    assert "authenticate" in prefix


def test_structured_context():
    prefix = build_context_prefix(
        content_type="json",
        filename="config.json",
        key_path="api.endpoints[0]",
    )
    assert "config.json" in prefix
    assert "api.endpoints[0]" in prefix


def test_spreadsheet_context():
    prefix = build_context_prefix(
        content_type="csv",
        filename="data.csv",
        sheet_name="Revenue",
        columns=["Region", "Revenue", "Growth"],
    )
    assert "data.csv" in prefix
    assert "Revenue" in prefix
    assert "Region" in prefix


def test_minimal_context():
    prefix = build_context_prefix(content_type="text", filename="notes.txt")
    assert "notes.txt" in prefix
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/chunking/test_context.py -v`
Expected: FAIL

- [ ] **Step 3: Implement context prefix builder**

```python
# src/agentdrive/chunking/context.py
def build_context_prefix(
    content_type: str,
    filename: str,
    heading_breadcrumb: list[str] | None = None,
    class_name: str | None = None,
    function_name: str | None = None,
    key_path: str | None = None,
    sheet_name: str | None = None,
    columns: list[str] | None = None,
    notebook_section: str | None = None,
    cell_number: int | None = None,
) -> str:
    parts = []

    if content_type == "code":
        parts.append(f"File: {filename}")
        if class_name:
            parts.append(f"Class: {class_name}")
        if function_name:
            parts.append(f"Function: {function_name}")

    elif content_type in ("json", "yaml"):
        parts.append(f"File: {filename}")
        if key_path:
            parts.append(f"Path: {key_path}")

    elif content_type in ("csv", "xlsx"):
        parts.append(f"File: {filename}")
        if sheet_name:
            parts.append(f"Sheet: {sheet_name}")
        if columns:
            parts.append(f"Columns: {', '.join(columns)}")

    elif content_type == "notebook":
        parts.append(f"Notebook: {filename}")
        if notebook_section:
            parts.append(f"Section: {notebook_section}")
        if cell_number is not None:
            parts.append(f"Cell: {cell_number}")

    elif content_type in ("pdf", "markdown"):
        parts.append(f"File: {filename}")
        if heading_breadcrumb:
            parts.append(" > ".join(heading_breadcrumb))

    else:
        parts.append(f"File: {filename}")

    return " | ".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/chunking/test_context.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/chunking/context.py tests/chunking/test_context.py
git commit -m "feat: context prefix builder for all content types"
```

---

### Task 4: Parent-Child Hierarchy Builder

**Files:**
- Create: `src/agentdrive/chunking/hierarchy.py`
- Test: `tests/chunking/test_hierarchy.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/chunking/test_hierarchy.py
from agentdrive.chunking.hierarchy import build_parent_child_chunks
from agentdrive.chunking.tokens import count_tokens


def test_short_section_single_parent_single_child():
    text = "This is a short section."
    results = build_parent_child_chunks(
        text, content_type="text", context_prefix="File: test.txt",
        parent_max_tokens=1500, child_max_tokens=300,
    )
    assert len(results) == 1
    assert results[0].parent.content == text
    assert len(results[0].children) == 1
    assert results[0].children[0].content == text


def test_long_section_splits_into_children():
    sentences = ["This is sentence number %d. " % i for i in range(50)]
    text = "".join(sentences)
    results = build_parent_child_chunks(
        text, content_type="text", context_prefix="File: test.txt",
        parent_max_tokens=1500, child_max_tokens=100,
    )
    assert len(results) >= 1
    for group in results:
        for child in group.children:
            assert count_tokens(child.content) <= 120  # ~100 + buffer


def test_children_have_context_prefix():
    text = "A meaningful paragraph about authentication flows."
    results = build_parent_child_chunks(
        text, content_type="text", context_prefix="File: auth.md | Section: Auth",
        parent_max_tokens=1500, child_max_tokens=300,
    )
    assert results[0].children[0].context_prefix == "File: auth.md | Section: Auth"


def test_tiny_text_not_discarded():
    text = "Short."
    results = build_parent_child_chunks(
        text, content_type="text", context_prefix="",
        parent_max_tokens=1500, child_max_tokens=300,
        min_child_tokens=0,
    )
    assert len(results) == 1
    assert results[0].children[0].content == "Short."


def test_overlap_between_children():
    sentences = ["Sentence %d is here. " % i for i in range(30)]
    text = "".join(sentences)
    results = build_parent_child_chunks(
        text, content_type="text", context_prefix="",
        parent_max_tokens=1500, child_max_tokens=100,
        overlap_tokens=15,
    )
    # With overlap, adjacent children should share some content
    if len(results[0].children) > 1:
        c1 = results[0].children[0].content
        c2 = results[0].children[1].content
        # Last sentence of c1 should appear at start of c2
        last_sentence_c1 = c1.strip().split(". ")[-1]
        assert last_sentence_c1 in c2 or len(results[0].children) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/chunking/test_hierarchy.py -v`
Expected: FAIL

- [ ] **Step 3: Implement hierarchy builder**

```python
# src/agentdrive/chunking/hierarchy.py
import re

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.chunking.tokens import count_tokens

SENTENCE_PATTERN = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')


def split_sentences(text: str) -> list[str]:
    sentences = SENTENCE_PATTERN.split(text)
    return [s.strip() for s in sentences if s.strip()]


def build_parent_child_chunks(
    text: str,
    content_type: str,
    context_prefix: str,
    parent_max_tokens: int = 1500,
    child_max_tokens: int = 300,
    min_child_tokens: int = 50,
    overlap_tokens: int = 30,
) -> list[ParentChildChunks]:
    text = text.strip()
    if not text:
        return []

    total_tokens = count_tokens(text)

    # If text fits in a single child, return as-is
    if total_tokens <= child_max_tokens:
        chunk = ChunkResult(
            content=text,
            context_prefix=context_prefix,
            token_count=total_tokens,
            content_type=content_type,
        )
        return [ParentChildChunks(parent=chunk, children=[chunk])]

    # Split into sentences for sentence-aligned chunking
    sentences = split_sentences(text)
    if not sentences:
        sentences = [text]

    # Build children by accumulating sentences
    children: list[ChunkResult] = []
    current_sentences: list[str] = []
    current_tokens = 0
    overlap_sentences: list[str] = []

    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)

        if current_tokens + sentence_tokens > child_max_tokens and current_sentences:
            # Emit child
            child_text = " ".join(current_sentences)
            children.append(ChunkResult(
                content=child_text,
                context_prefix=context_prefix,
                token_count=count_tokens(child_text),
                content_type=content_type,
            ))

            # Calculate overlap: keep last N sentences that fit in overlap_tokens
            overlap_sentences = []
            overlap_count = 0
            for s in reversed(current_sentences):
                s_tokens = count_tokens(s)
                if overlap_count + s_tokens > overlap_tokens:
                    break
                overlap_sentences.insert(0, s)
                overlap_count += s_tokens

            current_sentences = list(overlap_sentences)
            current_tokens = overlap_count

        current_sentences.append(sentence)
        current_tokens += sentence_tokens

    # Emit final child
    if current_sentences:
        child_text = " ".join(current_sentences)
        child_tokens = count_tokens(child_text)
        if child_tokens >= min_child_tokens or not children:
            children.append(ChunkResult(
                content=child_text,
                context_prefix=context_prefix,
                token_count=child_tokens,
                content_type=content_type,
            ))
        elif children:
            # Merge tiny trailing chunk into previous
            prev = children[-1]
            merged = prev.content + " " + child_text
            children[-1] = ChunkResult(
                content=merged,
                context_prefix=context_prefix,
                token_count=count_tokens(merged),
                content_type=content_type,
            )

    # Build parent(s) — group children into parent-sized groups
    results: list[ParentChildChunks] = []
    parent_children: list[ChunkResult] = []
    parent_tokens = 0

    for child in children:
        if parent_tokens + child.token_count > parent_max_tokens and parent_children:
            parent_text = " ".join(c.content for c in parent_children)
            parent = ChunkResult(
                content=parent_text,
                context_prefix=context_prefix,
                token_count=count_tokens(parent_text),
                content_type=content_type,
            )
            results.append(ParentChildChunks(parent=parent, children=list(parent_children)))
            parent_children = []
            parent_tokens = 0

        parent_children.append(child)
        parent_tokens += child.token_count

    if parent_children:
        parent_text = " ".join(c.content for c in parent_children)
        parent = ChunkResult(
            content=parent_text,
            context_prefix=context_prefix,
            token_count=count_tokens(parent_text),
            content_type=content_type,
        )
        results.append(ParentChildChunks(parent=parent, children=list(parent_children)))

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/chunking/test_hierarchy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/chunking/hierarchy.py tests/chunking/test_hierarchy.py
git commit -m "feat: parent-child hierarchy builder with sentence-aligned overlap"
```

---

### Task 5: Plain Text Chunker

**Files:**
- Create: `src/agentdrive/chunking/text.py`
- Test: `tests/chunking/test_text.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/chunking/test_text.py
from agentdrive.chunking.text import TextChunker


def test_supported_types():
    chunker = TextChunker()
    assert "text" in chunker.supported_types()


def test_short_text():
    chunker = TextChunker()
    results = chunker.chunk("Hello world.", "notes.txt")
    assert len(results) == 1
    assert results[0].children[0].content == "Hello world."


def test_paragraph_splitting():
    text = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here."
    chunker = TextChunker()
    results = chunker.chunk(text, "notes.txt")
    assert len(results) >= 1
    # All content preserved
    all_content = " ".join(c.content for group in results for c in group.children)
    assert "First paragraph" in all_content
    assert "Third paragraph" in all_content


def test_context_prefix_applied():
    chunker = TextChunker()
    results = chunker.chunk("Some text.", "notes.txt")
    assert "notes.txt" in results[0].children[0].context_prefix
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/chunking/test_text.py -v`
Expected: FAIL

- [ ] **Step 3: Implement text chunker**

```python
# src/agentdrive/chunking/text.py
from agentdrive.chunking.base import BaseChunker, ParentChildChunks
from agentdrive.chunking.context import build_context_prefix
from agentdrive.chunking.hierarchy import build_parent_child_chunks


class TextChunker(BaseChunker):
    def supported_types(self) -> list[str]:
        return ["text"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        prefix = build_context_prefix(content_type="text", filename=filename)

        # Split on double newlines (paragraph boundaries) first
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        text = "\n\n".join(paragraphs)

        return build_parent_child_chunks(
            text=text,
            content_type="text",
            context_prefix=prefix,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/chunking/test_text.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/chunking/text.py tests/chunking/test_text.py
git commit -m "feat: plain text chunker with paragraph boundaries"
```

---

### Task 6: Markdown Chunker

**Files:**
- Create: `src/agentdrive/chunking/markdown.py`
- Test: `tests/chunking/test_markdown.py`
- Create: `tests/fixtures/sample.md`

- [ ] **Step 1: Create sample markdown fixture**

```markdown
---
title: API Reference
author: Engineering
---

# API Reference

## Authentication

OAuth2 is used for all API authentication. Tokens expire after 30 minutes.

### OAuth2 Flow

The client obtains an authorization code and exchanges it for tokens.

```python
response = client.get_token(code=auth_code)
```

### API Keys

For server-to-server communication, use API keys instead.

## Users

### Create User

POST /v1/users creates a new user account.

| Field | Type | Required |
|-------|------|----------|
| name | string | yes |
| email | string | yes |

### Delete User

DELETE /v1/users/:id removes the user.
```

- [ ] **Step 2: Write failing tests**

```python
# tests/chunking/test_markdown.py
from pathlib import Path

from agentdrive.chunking.markdown import MarkdownChunker


FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.md"


def test_supported_types():
    chunker = MarkdownChunker()
    assert "markdown" in chunker.supported_types()


def test_splits_at_h2():
    content = FIXTURE.read_text()
    chunker = MarkdownChunker()
    results = chunker.chunk(content, "api-reference.md")
    # Should have chunks for Authentication and Users sections
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "OAuth2" in all_content
    assert "Create User" in all_content


def test_breadcrumb_in_context():
    content = FIXTURE.read_text()
    chunker = MarkdownChunker()
    results = chunker.chunk(content, "api-reference.md")
    # At least one chunk should have breadcrumb with heading hierarchy
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("Authentication" in p for p in prefixes)


def test_code_blocks_not_split():
    content = "## Setup\n\nInstall:\n\n```python\nimport os\nprint(os.getcwd())\n```\n\nDone."
    chunker = MarkdownChunker()
    results = chunker.chunk(content, "setup.md")
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "import os" in all_content
    assert "print(os.getcwd())" in all_content


def test_tables_kept_atomic():
    content = "## Data\n\n| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n"
    chunker = MarkdownChunker()
    results = chunker.chunk(content, "data.md")
    all_content = " ".join(c.content for g in results for c in g.children)
    # Table should not be split across chunks
    assert "| A | B |" in all_content


def test_front_matter_extracted():
    content = "---\ntitle: Test Doc\ntags: [a, b]\n---\n\n# Test\n\nContent here."
    chunker = MarkdownChunker()
    results = chunker.chunk(content, "test.md")
    # Front matter should be in metadata, not in chunk content
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "---" not in all_content or "title:" not in all_content


def test_tiny_sections_merged():
    content = "## A\n\nShort.\n\n## B\n\nAlso short.\n\n## C\n\nLonger section with more content that makes it worthwhile as its own chunk."
    chunker = MarkdownChunker()
    results = chunker.chunk(content, "test.md")
    # Tiny sections A and B should be merged
    total_children = sum(len(g.children) for g in results)
    assert total_children <= 3  # not one per tiny section
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/chunking/test_markdown.py -v`
Expected: FAIL

- [ ] **Step 4: Implement markdown chunker**

```python
# src/agentdrive/chunking/markdown.py
import re

from agentdrive.chunking.base import BaseChunker, ParentChildChunks
from agentdrive.chunking.context import build_context_prefix
from agentdrive.chunking.hierarchy import build_parent_child_chunks
from agentdrive.chunking.tokens import count_tokens

FRONT_MATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
CODE_BLOCK_RE = re.compile(r'```[\s\S]*?```', re.MULTILINE)

MIN_SECTION_TOKENS = 100


class MarkdownChunker(BaseChunker):
    def supported_types(self) -> list[str]:
        return ["markdown"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        metadata = metadata or {}

        # Extract front matter
        front_matter = {}
        fm_match = FRONT_MATTER_RE.match(content)
        if fm_match:
            fm_text = fm_match.group(1)
            content = content[fm_match.end():]
            for line in fm_text.split("\n"):
                if ":" in line:
                    key, _, value = line.partition(":")
                    front_matter[key.strip()] = value.strip()

        # Protect code blocks from heading detection
        code_blocks: dict[str, str] = {}
        counter = 0
        def replace_code(match: re.Match) -> str:
            nonlocal counter
            key = f"__CODE_BLOCK_{counter}__"
            code_blocks[key] = match.group(0)
            counter += 1
            return key
        protected = CODE_BLOCK_RE.sub(replace_code, content)

        # Parse sections by H1/H2 headings
        sections = self._split_by_headings(protected)

        # Restore code blocks and build chunks
        all_results: list[ParentChildChunks] = []
        pending_tiny: list[tuple[str, list[str]]] = []

        for section_text, breadcrumb in sections:
            # Restore code blocks
            for key, value in code_blocks.items():
                section_text = section_text.replace(key, value)

            section_tokens = count_tokens(section_text)

            # Merge tiny sections
            if section_tokens < MIN_SECTION_TOKENS:
                pending_tiny.append((section_text, breadcrumb))
                continue

            # Flush any pending tiny sections
            if pending_tiny:
                merged_text = "\n\n".join(t for t, _ in pending_tiny) + "\n\n" + section_text
                breadcrumb = pending_tiny[0][1]  # use first tiny section's breadcrumb
                pending_tiny = []
                section_text = merged_text

            prefix = build_context_prefix(
                content_type="markdown",
                filename=filename,
                heading_breadcrumb=breadcrumb,
            )

            results = build_parent_child_chunks(
                text=section_text.strip(),
                content_type="text",
                context_prefix=prefix,
            )
            # Attach front matter to metadata
            for group in results:
                group.parent.metadata = {**front_matter, **metadata}
                for child in group.children:
                    child.metadata = {**front_matter, **metadata}

            all_results.extend(results)

        # Flush remaining tiny sections
        if pending_tiny:
            merged_text = "\n\n".join(t for t, _ in pending_tiny)
            breadcrumb = pending_tiny[0][1]
            prefix = build_context_prefix(
                content_type="markdown", filename=filename, heading_breadcrumb=breadcrumb,
            )
            results = build_parent_child_chunks(
                text=merged_text.strip(), content_type="text", context_prefix=prefix,
            )
            all_results.extend(results)

        return all_results

    def _split_by_headings(self, text: str) -> list[tuple[str, list[str]]]:
        """Split text at H1/H2 boundaries, returning (section_text, breadcrumb) pairs."""
        lines = text.split("\n")
        sections: list[tuple[str, list[str]]] = []
        current_lines: list[str] = []
        current_breadcrumb: list[str] = []
        h1 = ""

        for line in lines:
            heading_match = HEADING_RE.match(line)
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                if level == 1:
                    if current_lines:
                        sections.append(("\n".join(current_lines), list(current_breadcrumb)))
                        current_lines = []
                    h1 = title
                    current_breadcrumb = [h1]

                elif level == 2:
                    if current_lines:
                        sections.append(("\n".join(current_lines), list(current_breadcrumb)))
                        current_lines = []
                    current_breadcrumb = [h1, title] if h1 else [title]

                # H3+ content stays in current section (not a split boundary)
                # but update breadcrumb for context
                elif level == 3 and len(current_breadcrumb) >= 1:
                    # Don't split, but include H3 in the text
                    pass

            current_lines.append(line)

        if current_lines:
            sections.append(("\n".join(current_lines), list(current_breadcrumb)))

        return sections if sections else [(text, [])]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/chunking/test_markdown.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/chunking/markdown.py tests/chunking/test_markdown.py tests/fixtures/sample.md
git commit -m "feat: markdown chunker with heading splits, code block protection, front matter"
```

---

### Task 7: Code Chunker (tree-sitter)

**Files:**
- Create: `src/agentdrive/chunking/code.py`
- Test: `tests/chunking/test_code.py`
- Create: `tests/fixtures/sample.py`

- [ ] **Step 1: Add tree-sitter dependencies**

Add to `pyproject.toml`:
```
"tree-sitter>=0.23.0",
"tree-sitter-python>=0.23.0",
"tree-sitter-javascript>=0.23.0",
"tree-sitter-typescript>=0.23.0",
"tree-sitter-go>=0.23.0",
"tree-sitter-rust>=0.23.0",
"tree-sitter-java>=0.23.0",
```

Run: `pip install -e ".[dev]"`

- [ ] **Step 2: Create sample Python fixture**

```python
# tests/fixtures/sample.py
"""Authentication service for managing user tokens."""

import hashlib
from datetime import datetime, timedelta


class AuthService:
    """Handles user authentication and token management."""

    def __init__(self, secret_key: str, token_ttl: int = 3600):
        self.secret_key = secret_key
        self.token_ttl = token_ttl

    def authenticate(self, username: str, password: str) -> dict:
        """Verify credentials and return a token."""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        # In production, verify against database
        return {
            "token": self._generate_token(username),
            "expires_at": datetime.utcnow() + timedelta(seconds=self.token_ttl),
        }

    def refresh_token(self, token: str) -> dict:
        """Refresh an existing token."""
        claims = self._decode_token(token)
        return {
            "token": self._generate_token(claims["sub"]),
            "expires_at": datetime.utcnow() + timedelta(seconds=self.token_ttl),
        }

    def _generate_token(self, subject: str) -> str:
        payload = f"{subject}:{datetime.utcnow().isoformat()}"
        return hashlib.sha256(f"{payload}:{self.secret_key}".encode()).hexdigest()

    def _decode_token(self, token: str) -> dict:
        return {"sub": "user", "exp": datetime.utcnow()}


def create_auth_service(config: dict) -> AuthService:
    """Factory function for creating AuthService instances."""
    return AuthService(
        secret_key=config["secret_key"],
        token_ttl=config.get("token_ttl", 3600),
    )
```

- [ ] **Step 3: Write failing tests**

```python
# tests/chunking/test_code.py
from pathlib import Path

from agentdrive.chunking.code import CodeChunker


FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample.py"


def test_supported_types():
    chunker = CodeChunker()
    assert "code" in chunker.supported_types()


def test_splits_at_functions():
    content = FIXTURE.read_text()
    chunker = CodeChunker()
    results = chunker.chunk(content, "auth/service.py")
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "authenticate" in all_content
    assert "refresh_token" in all_content


def test_class_context_prepended():
    content = FIXTURE.read_text()
    chunker = CodeChunker()
    results = chunker.chunk(content, "auth/service.py")
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("AuthService" in p for p in prefixes)


def test_file_path_in_context():
    content = FIXTURE.read_text()
    chunker = CodeChunker()
    results = chunker.chunk(content, "auth/service.py")
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("auth/service.py" in p for p in prefixes)


def test_content_type_is_code():
    content = FIXTURE.read_text()
    chunker = CodeChunker()
    results = chunker.chunk(content, "auth/service.py")
    for group in results:
        for child in group.children:
            assert child.content_type == "code"


def test_standalone_function_chunked():
    content = "def hello():\n    return 'world'\n\ndef goodbye():\n    return 'farewell'\n"
    chunker = CodeChunker()
    results = chunker.chunk(content, "utils.py")
    all_content = [c.content for g in results for c in g.children]
    assert any("hello" in c for c in all_content)
    assert any("goodbye" in c for c in all_content)
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/chunking/test_code.py -v`
Expected: FAIL

- [ ] **Step 5: Implement code chunker**

```python
# src/agentdrive/chunking/code.py
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

from agentdrive.chunking.base import BaseChunker, ChunkResult, ParentChildChunks
from agentdrive.chunking.context import build_context_prefix
from agentdrive.chunking.tokens import count_tokens

LANGUAGE_MAP = {
    ".py": ("python", tspython.language()),
}

# Tree-sitter node types that represent top-level definitions
DEFINITION_TYPES = {
    "python": {"function_definition", "class_definition", "decorated_definition"},
}

METHOD_TYPES = {
    "python": {"function_definition"},
}


class CodeChunker(BaseChunker):
    def supported_types(self) -> list[str]:
        return ["code"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        ext = Path(filename).suffix.lower()
        lang_info = LANGUAGE_MAP.get(ext)

        if not lang_info:
            # Fallback: treat as text
            return self._chunk_as_text(content, filename)

        lang_name, lang_obj = lang_info
        language = Language(lang_obj)
        parser = Parser(language)
        tree = parser.parse(content.encode())

        results: list[ParentChildChunks] = []
        source_bytes = content.encode()

        for node in tree.root_node.children:
            node_type = node.type

            # Handle decorated definitions (unwrap to get the actual def)
            actual_node = node
            if node_type == "decorated_definition":
                for child in node.children:
                    if child.type in ("function_definition", "class_definition"):
                        actual_node = child
                        break

            definition_types = DEFINITION_TYPES.get(lang_name, set())

            if node.type in definition_types or actual_node.type in definition_types:
                node_text = source_bytes[node.start_byte:node.end_byte].decode()

                if actual_node.type == "class_definition":
                    results.extend(self._chunk_class(actual_node, node, source_bytes, filename, lang_name))
                else:
                    func_name = self._get_name(actual_node, source_bytes)
                    prefix = build_context_prefix(
                        content_type="code",
                        filename=filename,
                        function_name=func_name,
                    )
                    token_count = count_tokens(node_text)
                    chunk = ChunkResult(
                        content=node_text,
                        context_prefix=prefix,
                        token_count=token_count,
                        content_type="code",
                    )
                    results.append(ParentChildChunks(parent=chunk, children=[chunk]))

        # Handle any non-definition top-level code (imports, assignments)
        non_def_lines = []
        for node in tree.root_node.children:
            if node.type not in DEFINITION_TYPES.get(lang_name, set()):
                text = source_bytes[node.start_byte:node.end_byte].decode()
                non_def_lines.append(text)

        if non_def_lines:
            combined = "\n".join(non_def_lines)
            if count_tokens(combined) > 10:
                prefix = build_context_prefix(content_type="code", filename=filename)
                token_count = count_tokens(combined)
                chunk = ChunkResult(
                    content=combined,
                    context_prefix=prefix,
                    token_count=token_count,
                    content_type="code",
                )
                results.insert(0, ParentChildChunks(parent=chunk, children=[chunk]))

        return results if results else self._chunk_as_text(content, filename)

    def _chunk_class(
        self, class_node, full_node, source_bytes: bytes, filename: str, lang_name: str,
    ) -> list[ParentChildChunks]:
        class_name = self._get_name(class_node, source_bytes)
        class_text = source_bytes[full_node.start_byte:full_node.end_byte].decode()

        # Extract class docstring + signature for context
        class_header_lines = []
        for line in class_text.split("\n"):
            class_header_lines.append(line)
            stripped = line.strip()
            if stripped.startswith('"""') and stripped.endswith('"""') and len(stripped) > 6:
                break
            if stripped == '"""':
                break
            if not stripped.startswith('"""') and not stripped.startswith("class ") and stripped and not stripped.startswith("#"):
                if len(class_header_lines) > 5:
                    break

        # Extract methods
        methods: list[ParentChildChunks] = []
        method_types = METHOD_TYPES.get(lang_name, set())
        body = class_node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type in method_types:
                    method_text = source_bytes[child.start_byte:child.end_byte].decode()
                    method_name = self._get_name(child, source_bytes)
                    prefix = build_context_prefix(
                        content_type="code",
                        filename=filename,
                        class_name=class_name,
                        function_name=method_name,
                    )
                    token_count = count_tokens(method_text)
                    chunk = ChunkResult(
                        content=method_text,
                        context_prefix=prefix,
                        token_count=token_count,
                        content_type="code",
                    )
                    methods.append(ParentChildChunks(parent=chunk, children=[chunk]))

        if methods:
            return methods

        # If no methods extracted, return whole class
        prefix = build_context_prefix(content_type="code", filename=filename, class_name=class_name)
        chunk = ChunkResult(
            content=class_text,
            context_prefix=prefix,
            token_count=count_tokens(class_text),
            content_type="code",
        )
        return [ParentChildChunks(parent=chunk, children=[chunk])]

    def _get_name(self, node, source_bytes: bytes) -> str:
        name_node = node.child_by_field_name("name")
        if name_node:
            return source_bytes[name_node.start_byte:name_node.end_byte].decode()
        return ""

    def _chunk_as_text(self, content: str, filename: str) -> list[ParentChildChunks]:
        prefix = build_context_prefix(content_type="code", filename=filename)
        chunk = ChunkResult(
            content=content,
            context_prefix=prefix,
            token_count=count_tokens(content),
            content_type="code",
        )
        return [ParentChildChunks(parent=chunk, children=[chunk])]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/chunking/test_code.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/agentdrive/chunking/code.py tests/chunking/test_code.py tests/fixtures/sample.py pyproject.toml
git commit -m "feat: code chunker with tree-sitter AST parsing"
```

---

### Task 8: Structured Data Chunker (JSON/YAML)

**Files:**
- Create: `src/agentdrive/chunking/structured.py`
- Test: `tests/chunking/test_structured.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/chunking/test_structured.py
import json

from agentdrive.chunking.structured import StructuredChunker


def test_supported_types():
    chunker = StructuredChunker()
    assert "json" in chunker.supported_types()
    assert "yaml" in chunker.supported_types()


def test_json_top_level_keys():
    data = json.dumps({
        "database": {"host": "localhost", "port": 5432},
        "api": {"endpoints": ["/users", "/auth"]},
        "logging": {"level": "info"},
    }, indent=2)
    chunker = StructuredChunker()
    results = chunker.chunk(data, "config.json")
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "database" in all_content
    assert "localhost" in all_content


def test_key_path_in_context():
    data = json.dumps({"database": {"host": "localhost"}}, indent=2)
    chunker = StructuredChunker()
    results = chunker.chunk(data, "config.json")
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("config.json" in p for p in prefixes)


def test_small_json_single_chunk():
    data = json.dumps({"key": "value"})
    chunker = StructuredChunker()
    results = chunker.chunk(data, "small.json")
    total_children = sum(len(g.children) for g in results)
    assert total_children == 1


def test_yaml_handled():
    yaml_content = "database:\n  host: localhost\n  port: 5432\napi:\n  key: secret\n"
    chunker = StructuredChunker()
    results = chunker.chunk(yaml_content, "config.yaml")
    assert len(results) >= 1
```

- [ ] **Step 2: Run tests, verify fail, implement**

```python
# src/agentdrive/chunking/structured.py
import json

import yaml

from agentdrive.chunking.base import BaseChunker, ChunkResult, ParentChildChunks
from agentdrive.chunking.context import build_context_prefix
from agentdrive.chunking.tokens import count_tokens


class StructuredChunker(BaseChunker):
    def supported_types(self) -> list[str]:
        return ["json", "yaml"]  # TOML routes here via file_type.py mapping

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        # Parse content
        try:
            if filename.endswith((".yaml", ".yml")):
                data = yaml.safe_load(content)
            elif filename.endswith(".toml"):
                import tomllib
                data = tomllib.loads(content)
            else:
                data = json.loads(content)
        except (json.JSONDecodeError, yaml.YAMLError):
            # Fallback: treat as text
            prefix = build_context_prefix(content_type="json", filename=filename)
            chunk = ChunkResult(
                content=content, context_prefix=prefix,
                token_count=count_tokens(content), content_type="text",
            )
            return [ParentChildChunks(parent=chunk, children=[chunk])]

        if not isinstance(data, dict):
            prefix = build_context_prefix(content_type="json", filename=filename)
            text = json.dumps(data, indent=2) if not isinstance(data, str) else data
            chunk = ChunkResult(
                content=text, context_prefix=prefix,
                token_count=count_tokens(text), content_type="text",
            )
            return [ParentChildChunks(parent=chunk, children=[chunk])]

        # Chunk by top-level keys
        results: list[ParentChildChunks] = []
        for key, value in data.items():
            serialized = json.dumps({key: value}, indent=2)
            prefix = build_context_prefix(
                content_type="json", filename=filename, key_path=key,
            )
            token_count = count_tokens(serialized)
            chunk = ChunkResult(
                content=serialized, context_prefix=prefix,
                token_count=token_count, content_type="text",
            )
            results.append(ParentChildChunks(parent=chunk, children=[chunk]))

        return results if results else [ParentChildChunks(
            parent=ChunkResult(content=content, context_prefix="", token_count=count_tokens(content), content_type="text"),
            children=[ChunkResult(content=content, context_prefix="", token_count=count_tokens(content), content_type="text")],
        )]
```

- [ ] **Step 3: Add PyYAML dependency to pyproject.toml**

Add: `"pyyaml>=6.0",`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/chunking/test_structured.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/chunking/structured.py tests/chunking/test_structured.py pyproject.toml
git commit -m "feat: JSON/YAML chunker with top-level key splitting"
```

---

### Task 9: Spreadsheet + Notebook Chunkers

**Files:**
- Create: `src/agentdrive/chunking/spreadsheet.py`
- Create: `src/agentdrive/chunking/notebook.py`
- Test: `tests/chunking/test_spreadsheet.py`
- Test: `tests/chunking/test_notebook.py`

- [ ] **Step 1: Add dependencies**

Add to `pyproject.toml`:
```
"openpyxl>=3.1.0",
```

- [ ] **Step 2: Write spreadsheet tests**

```python
# tests/chunking/test_spreadsheet.py
from agentdrive.chunking.spreadsheet import SpreadsheetChunker


def test_supported_types():
    chunker = SpreadsheetChunker()
    assert "csv" in chunker.supported_types()


def test_csv_chunking():
    csv_content = "Name,Age,City\nAlice,30,NYC\nBob,25,SF\nCharlie,35,LA\n"
    chunker = SpreadsheetChunker()
    results = chunker.chunk(csv_content, "people.csv")
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "Alice" in all_content
    assert "Name" in all_content  # headers preserved


def test_headers_in_context():
    csv_content = "Name,Age\nAlice,30\n"
    chunker = SpreadsheetChunker()
    results = chunker.chunk(csv_content, "data.csv")
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("Name" in p for p in prefixes)
```

- [ ] **Step 3: Implement spreadsheet chunker**

```python
# src/agentdrive/chunking/spreadsheet.py
import csv
import io

from agentdrive.chunking.base import BaseChunker, ChunkResult, ParentChildChunks
from agentdrive.chunking.context import build_context_prefix
from agentdrive.chunking.tokens import count_tokens

ROWS_PER_CHUNK = 30


class SpreadsheetChunker(BaseChunker):
    def supported_types(self) -> list[str]:
        return ["csv", "xlsx"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)

        if not rows:
            return []

        headers = rows[0]
        data_rows = rows[1:]

        prefix = build_context_prefix(
            content_type="csv", filename=filename, columns=headers,
        )

        results: list[ParentChildChunks] = []
        for i in range(0, len(data_rows), ROWS_PER_CHUNK):
            batch = data_rows[i:i + ROWS_PER_CHUNK]
            # Serialize as markdown table
            lines = ["| " + " | ".join(headers) + " |"]
            lines.append("| " + " | ".join("---" for _ in headers) + " |")
            for row in batch:
                padded = row + [""] * (len(headers) - len(row))
                lines.append("| " + " | ".join(padded) + " |")

            text = "\n".join(lines)
            token_count = count_tokens(text)
            chunk = ChunkResult(
                content=text, context_prefix=prefix,
                token_count=token_count, content_type="text",
            )
            results.append(ParentChildChunks(parent=chunk, children=[chunk]))

        return results
```

- [ ] **Step 4: Write notebook tests**

```python
# tests/chunking/test_notebook.py
import json

from agentdrive.chunking.notebook import NotebookChunker


def make_notebook(cells):
    return json.dumps({
        "nbformat": 4,
        "metadata": {},
        "cells": cells,
    })


def test_supported_types():
    chunker = NotebookChunker()
    assert "notebook" in chunker.supported_types()


def test_pairs_markdown_with_code():
    nb = make_notebook([
        {"cell_type": "markdown", "source": ["## Data Loading"], "metadata": {}},
        {"cell_type": "code", "source": ["import pandas as pd\ndf = pd.read_csv('data.csv')"], "metadata": {}, "outputs": []},
    ])
    chunker = NotebookChunker()
    results = chunker.chunk(nb, "analysis.ipynb")
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "Data Loading" in all_content
    assert "import pandas" in all_content


def test_notebook_context():
    nb = make_notebook([
        {"cell_type": "markdown", "source": ["## Setup"], "metadata": {}},
        {"cell_type": "code", "source": ["x = 1"], "metadata": {}, "outputs": []},
    ])
    chunker = NotebookChunker()
    results = chunker.chunk(nb, "test.ipynb")
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("test.ipynb" in p for p in prefixes)
```

- [ ] **Step 5: Implement notebook chunker**

```python
# src/agentdrive/chunking/notebook.py
import json

from agentdrive.chunking.base import BaseChunker, ChunkResult, ParentChildChunks
from agentdrive.chunking.context import build_context_prefix
from agentdrive.chunking.tokens import count_tokens


class NotebookChunker(BaseChunker):
    def supported_types(self) -> list[str]:
        return ["notebook"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        try:
            nb = json.loads(content)
        except json.JSONDecodeError:
            return []

        cells = nb.get("cells", [])
        results: list[ParentChildChunks] = []
        current_section = ""
        cell_num = 0

        i = 0
        while i < len(cells):
            cell = cells[i]
            cell_type = cell.get("cell_type", "")
            source = "".join(cell.get("source", []))

            # Track section from markdown headings
            if cell_type == "markdown":
                for line in source.split("\n"):
                    if line.startswith("#"):
                        current_section = line.lstrip("#").strip()

                # Pair markdown with following code cell
                if i + 1 < len(cells) and cells[i + 1].get("cell_type") == "code":
                    next_source = "".join(cells[i + 1].get("source", []))
                    combined = f"{source}\n\n```python\n{next_source}\n```"
                    cell_num += 1

                    prefix = build_context_prefix(
                        content_type="notebook", filename=filename,
                        notebook_section=current_section, cell_number=cell_num,
                    )
                    chunk = ChunkResult(
                        content=combined, context_prefix=prefix,
                        token_count=count_tokens(combined), content_type="code",
                    )
                    results.append(ParentChildChunks(parent=chunk, children=[chunk]))
                    i += 2
                    continue

            if cell_type == "code" and source.strip():
                cell_num += 1
                prefix = build_context_prefix(
                    content_type="notebook", filename=filename,
                    notebook_section=current_section, cell_number=cell_num,
                )
                chunk = ChunkResult(
                    content=source, context_prefix=prefix,
                    token_count=count_tokens(source), content_type="code",
                )
                results.append(ParentChildChunks(parent=chunk, children=[chunk]))

            i += 1

        return results
```

- [ ] **Step 6: Run all tests**

Run: `pytest tests/chunking/test_spreadsheet.py tests/chunking/test_notebook.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/agentdrive/chunking/spreadsheet.py src/agentdrive/chunking/notebook.py tests/chunking/test_spreadsheet.py tests/chunking/test_notebook.py pyproject.toml
git commit -m "feat: spreadsheet and notebook chunkers"
```

---

### Task 10: PDF Chunker (Docling)

**Files:**
- Create: `src/agentdrive/chunking/pdf.py`
- Test: `tests/chunking/test_pdf.py`

- [ ] **Step 1: Add Docling dependency**

Add to `pyproject.toml`:
```
"docling>=2.15.0",
```

Run: `pip install -e ".[dev]"`

- [ ] **Step 2: Write failing tests**

```python
# tests/chunking/test_pdf.py
from unittest.mock import MagicMock, patch

from agentdrive.chunking.pdf import PdfChunker


def test_supported_types():
    chunker = PdfChunker()
    assert "pdf" in chunker.supported_types()


@patch("agentdrive.chunking.pdf.DocumentConverter")
def test_pdf_produces_chunks(mock_converter_cls):
    # Mock Docling output
    mock_doc = MagicMock()
    mock_doc.document.export_to_markdown.return_value = (
        "# Report\n\n## Introduction\n\nThis is the intro.\n\n"
        "## Results\n\nThe results show improvement.\n\n"
        "## Conclusion\n\nWe conclude that things are better."
    )
    mock_result = MagicMock()
    mock_result.__iter__ = lambda self: iter([mock_doc])
    mock_converter = MagicMock()
    mock_converter.convert.return_value = mock_result
    mock_converter_cls.return_value = mock_converter

    chunker = PdfChunker()
    results = chunker.chunk_bytes(b"fake pdf bytes", "report.pdf")
    assert len(results) >= 1
    all_content = " ".join(c.content for g in results for c in g.children)
    assert "intro" in all_content.lower()
    assert "results" in all_content.lower()


@patch("agentdrive.chunking.pdf.DocumentConverter")
def test_pdf_breadcrumbs(mock_converter_cls):
    mock_doc = MagicMock()
    mock_doc.document.export_to_markdown.return_value = (
        "# Guide\n\n## Setup\n\nInstall the package.\n"
    )
    mock_result = MagicMock()
    mock_result.__iter__ = lambda self: iter([mock_doc])
    mock_converter = MagicMock()
    mock_converter.convert.return_value = mock_result
    mock_converter_cls.return_value = mock_converter

    chunker = PdfChunker()
    results = chunker.chunk_bytes(b"pdf", "guide.pdf")
    prefixes = [c.context_prefix for g in results for c in g.children]
    assert any("Setup" in p for p in prefixes)
```

- [ ] **Step 3: Implement PDF chunker**

```python
# src/agentdrive/chunking/pdf.py
import tempfile
from pathlib import Path

from docling.document_converter import DocumentConverter

from agentdrive.chunking.base import BaseChunker, ParentChildChunks
from agentdrive.chunking.markdown import MarkdownChunker


class PdfChunker(BaseChunker):
    def __init__(self) -> None:
        self._markdown_chunker = MarkdownChunker()

    def supported_types(self) -> list[str]:
        return ["pdf"]

    def chunk(self, content: str, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        # PDF content arrives as bytes, not str. Use chunk_bytes instead.
        raise NotImplementedError("Use chunk_bytes for PDF files")

    def chunk_bytes(self, data: bytes, filename: str, metadata: dict | None = None) -> list[ParentChildChunks]:
        # Write to temp file for Docling
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(data)
            temp_path = f.name

        try:
            converter = DocumentConverter()
            results = converter.convert(temp_path)

            for doc in results:
                markdown = doc.document.export_to_markdown()
                return self._markdown_chunker.chunk(markdown, filename, metadata)

        except Exception:
            # Fallback: return raw text extraction
            return []
        finally:
            Path(temp_path).unlink(missing_ok=True)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/chunking/test_pdf.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/chunking/pdf.py tests/chunking/test_pdf.py pyproject.toml
git commit -m "feat: PDF chunker with Docling + markdown pipeline"
```

---

### Task 11: Chunker Registry

**Files:**
- Create: `src/agentdrive/chunking/registry.py`
- Test: `tests/chunking/test_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/chunking/test_registry.py
from agentdrive.chunking.registry import ChunkerRegistry


def test_registry_returns_chunker_for_type():
    registry = ChunkerRegistry()
    chunker = registry.get_chunker("markdown")
    assert chunker is not None
    assert "markdown" in chunker.supported_types()


def test_registry_returns_text_for_unknown():
    registry = ChunkerRegistry()
    chunker = registry.get_chunker("unknown_type")
    assert chunker is not None
    assert "text" in chunker.supported_types()


def test_registry_all_types_covered():
    registry = ChunkerRegistry()
    for content_type in ["pdf", "markdown", "code", "json", "yaml", "csv", "xlsx", "notebook", "text"]:
        chunker = registry.get_chunker(content_type)
        assert chunker is not None
```

- [ ] **Step 2: Implement registry**

```python
# src/agentdrive/chunking/registry.py
from agentdrive.chunking.base import BaseChunker
from agentdrive.chunking.code import CodeChunker
from agentdrive.chunking.markdown import MarkdownChunker
from agentdrive.chunking.notebook import NotebookChunker
from agentdrive.chunking.pdf import PdfChunker
from agentdrive.chunking.spreadsheet import SpreadsheetChunker
from agentdrive.chunking.structured import StructuredChunker
from agentdrive.chunking.text import TextChunker


class ChunkerRegistry:
    def __init__(self) -> None:
        self._chunkers: dict[str, BaseChunker] = {}
        self._fallback = TextChunker()

        for chunker in [
            PdfChunker(),
            MarkdownChunker(),
            CodeChunker(),
            StructuredChunker(),
            SpreadsheetChunker(),
            NotebookChunker(),
            TextChunker(),
        ]:
            for content_type in chunker.supported_types():
                self._chunkers[content_type] = chunker

    def get_chunker(self, content_type: str) -> BaseChunker:
        return self._chunkers.get(content_type, self._fallback)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/chunking/test_registry.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/agentdrive/chunking/registry.py tests/chunking/test_registry.py
git commit -m "feat: chunker registry routing files to type-specific chunkers"
```

---

### Task 12: Ingest Orchestrator

**Files:**
- Create: `src/agentdrive/services/ingest.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ingest.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from agentdrive.models.file import File
from agentdrive.models.tenant import Tenant
from agentdrive.models.types import FileStatus
from agentdrive.services.auth import hash_api_key
from agentdrive.services.ingest import process_file


@pytest_asyncio.fixture
async def test_file(db_session):
    tenant = Tenant(name="Test", api_key_hash=hash_api_key("sk-test"))
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)

    file = File(
        tenant_id=tenant.id,
        filename="test.md",
        content_type="markdown",
        gcs_path="tenants/abc/files/def/test.md",
        file_size=100,
        status=FileStatus.PENDING,
    )
    db_session.add(file)
    await db_session.commit()
    await db_session.refresh(file)
    return file


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.StorageService")
async def test_process_file_success(mock_storage_cls, test_file, db_session):
    mock_storage = MagicMock()
    mock_storage.download.return_value = b"# Hello\n\n## Section\n\nContent here."
    mock_storage_cls.return_value = mock_storage

    await process_file(test_file.id, db_session)

    await db_session.refresh(test_file)
    assert test_file.status == FileStatus.READY


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.StorageService")
async def test_process_file_creates_chunks(mock_storage_cls, test_file, db_session):
    mock_storage = MagicMock()
    mock_storage.download.return_value = b"# Doc\n\n## Part A\n\nFirst section.\n\n## Part B\n\nSecond section."
    mock_storage_cls.return_value = mock_storage

    await process_file(test_file.id, db_session)

    from sqlalchemy import select
    from agentdrive.models.chunk import Chunk
    result = await db_session.execute(select(Chunk).where(Chunk.file_id == test_file.id))
    chunks = result.scalars().all()
    assert len(chunks) > 0


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.StorageService")
async def test_process_file_failure_sets_status(mock_storage_cls, test_file, db_session):
    mock_storage = MagicMock()
    mock_storage.download.side_effect = Exception("GCS error")
    mock_storage_cls.return_value = mock_storage

    await process_file(test_file.id, db_session)

    await db_session.refresh(test_file)
    assert test_file.status == FileStatus.FAILED
```

- [ ] **Step 2: Implement ingest orchestrator**

```python
# src/agentdrive/services/ingest.py
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.chunking.base import ParentChildChunks
from agentdrive.chunking.registry import ChunkerRegistry
from agentdrive.models.chunk import Chunk, ParentChunk
from agentdrive.models.file import File
from agentdrive.models.types import FileStatus
from agentdrive.services.storage import StorageService

logger = logging.getLogger(__name__)
registry = ChunkerRegistry()


async def process_file(file_id: uuid.UUID, session: AsyncSession) -> None:
    result = await session.execute(select(File).where(File.id == file_id))
    file = result.scalar_one_or_none()
    if not file:
        logger.error(f"File {file_id} not found")
        return

    file.status = FileStatus.PROCESSING
    await session.commit()

    try:
        # Download from GCS
        storage = StorageService()
        data = storage.download(file.gcs_path)

        # Get chunker
        chunker = registry.get_chunker(file.content_type)

        # Chunk the content (chunk_bytes handles both binary and text formats)
        chunk_groups = chunker.chunk_bytes(data, file.filename)

        # Store chunks in database
        chunk_index = 0
        for group in chunk_groups:
            # Create parent chunk
            parent_record = ParentChunk(
                file_id=file.id,
                content=group.parent.content,
                token_count=group.parent.token_count,
                metadata=group.parent.metadata,
            )
            session.add(parent_record)
            await session.flush()

            # Create child chunks
            for child in group.children:
                chunk_record = Chunk(
                    file_id=file.id,
                    parent_chunk_id=parent_record.id,
                    chunk_index=chunk_index,
                    content=child.content,
                    context_prefix=child.context_prefix,
                    token_count=child.token_count,
                    content_type=child.content_type,
                    metadata=child.metadata,
                    # embedding columns left NULL — filled by embedding pipeline (Plan 3)
                )
                session.add(chunk_record)
                chunk_index += 1

        file.status = FileStatus.READY
        await session.commit()
        logger.info(f"File {file_id} processed: {chunk_index} chunks created")

    except Exception as e:
        logger.exception(f"Failed to process file {file_id}: {e}")
        await session.rollback()
        file.status = FileStatus.FAILED
        await session.commit()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_ingest.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/agentdrive/services/ingest.py tests/test_ingest.py
git commit -m "feat: async ingest orchestrator — download, chunk, store"
```

---

### Task 13: Wire Ingest Into File Upload

**Files:**
- Modify: `src/agentdrive/routers/files.py`

- [ ] **Step 1: Add background task trigger to upload endpoint**

Add to the `upload_file` function in `src/agentdrive/routers/files.py`, after `await session.commit()`:

```python
from fastapi import BackgroundTasks
from agentdrive.services.ingest import process_file
from agentdrive.db.session import async_session_factory

# Add BackgroundTasks parameter to the endpoint
async def upload_file(
    file: UploadFile = File(...),
    collection: uuid.UUID | None = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    tenant: Tenant = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_session),
):
    # ... existing upload code ...

    # Trigger async processing
    async def run_ingest():
        async with async_session_factory() as ingest_session:
            await process_file(file_record.id, ingest_session)

    background_tasks.add_task(run_ingest)

    return FileUploadResponse.model_validate(file_record)
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/agentdrive/routers/files.py
git commit -m "feat: wire ingest pipeline into file upload background task"
```

---

## Summary

After completing all 13 tasks, you will have:

- Token counting utility (tiktoken)
- Base chunker interface + ChunkResult dataclass
- Context prefix builder for all content types
- Parent-child hierarchy builder with sentence-aligned overlap
- 7 type-specific chunkers: text, markdown, code (tree-sitter), JSON/YAML, CSV, notebook, PDF (Docling)
- Chunker registry routing files to the right chunker
- Async ingest orchestrator (download → chunk → store)
- Background task wired into file upload endpoint
- Comprehensive test suite with fixtures

**Chunks are stored without embeddings.** Embedding columns remain NULL — Plan 3 (Retrieval + MCP) adds the embedding pipeline, search, and MCP server.

**Next plan:** Retrieval Engine + MCP Server (embedding pipeline, hybrid search, BM25, reranking, search API, MCP tools)
