# Hierarchical Summarization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a token threshold gate to Phase 2 summarization so documents over 200k tokens use map-reduce instead of a single LLM call.

**Architecture:** A `count_tokens` check in `_phase2_summarization` routes to the existing single-call path (≤200k) or a new hierarchical path (>200k). The hierarchical path batches parent chunks into ~50k-token groups, summarizes each concurrently, then reduces into the final `FileSummary`. Output contract is unchanged.

**Tech Stack:** Python asyncio, OpenAI SDK (Gemini via Google AI Studio), tiktoken, pytest

**Spec:** `docs/superpowers/specs/2026-04-03-hierarchical-summarization-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/agentdrive/enrichment/client.py` | Modify | Add `generate_group_summary()` and `generate_reduce_summary()` methods + prompts |
| `src/agentdrive/enrichment/contextual.py` | Modify | Add `generate_group_summary()` and `generate_reduce_summary()` thin wrappers |
| `src/agentdrive/services/ingest.py` | Modify | Add token gate, `_batch_parents()`, `_hierarchical_summarize()` |
| `tests/enrichment/test_client.py` | Modify | Tests for new client methods |
| `tests/test_summarization.py` | Create | Tests for batching logic and threshold routing |

---

### Task 1: Add map prompt and `generate_group_summary()` to EnrichmentClient

**Files:**
- Modify: `src/agentdrive/enrichment/client.py`
- Test: `tests/enrichment/test_client.py`

- [ ] **Step 1: Write failing test for `generate_group_summary`**

Add to `tests/enrichment/test_client.py`:

```python
@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_group_summary(mock_openai_cls):
    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = _mock_chat_response(
        '{"summary": "This section covers revenue.", "section_summaries": [{"heading": "Q3 Revenue", "summary": "Revenue grew 34%."}]}'
    )
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    result = await client.generate_group_summary(
        group_text="Q3 revenue reached $4.2M, up 34% YoY...",
        group_index=1,
        total_groups=4,
    )

    assert result["summary"] == "This section covers revenue."
    assert len(result["section_summaries"]) == 1
    call_args = mock_client.chat.completions.create.call_args
    assert call_args[1]["response_format"] == {"type": "json_object"}
    content = call_args[1]["messages"][0]["content"]
    assert "section 1 of 4" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/enrichment/test_client.py::test_generate_group_summary -v`
Expected: FAIL — `EnrichmentClient` has no attribute `generate_group_summary`

- [ ] **Step 3: Implement `generate_group_summary` in client.py**

Add prompt constant after `CONTEXT_WITH_SUMMARY_PROMPT` (after line 44):

```python
GROUP_SUMMARY_PROMPT = """You are summarizing section {group_index} of {total_groups} of a larger document. Produce:
1. A summary of this section (2-3 sentences)
2. section_summaries (a list of objects with "heading" and "summary" for each major section within this portion)

<document_section>
{group_text}
</document_section>

Return valid JSON with this exact structure:
{{"summary": "...", "section_summaries": [{{"heading": "...", "summary": "..."}}]}}"""
```

Add method to `EnrichmentClient` class (after `generate_summary`):

```python
async def generate_group_summary(
    self, group_text: str, group_index: int, total_groups: int
) -> dict:
    """Summarize a group of parent chunks (map phase of hierarchical summarization)."""
    try:
        response = await self._client.chat.completions.create(
            model=settings.enrichment_model,
            max_tokens=16384,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": GROUP_SUMMARY_PROMPT.format(
                        group_text=group_text,
                        group_index=group_index,
                        total_groups=total_groups,
                    ),
                }
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        return json.loads(text)
    except Exception as e:
        logger.warning(f"Group summary generation failed: {e}")
        return {"summary": "", "section_summaries": []}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/enrichment/test_client.py::test_generate_group_summary -v`
Expected: PASS

- [ ] **Step 5: Write failing test for error fallback**

Add to `tests/enrichment/test_client.py`:

```python
@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_group_summary_fallback_on_error(mock_openai_cls):
    mock_client = AsyncMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    result = await client.generate_group_summary("text", 1, 4)

    assert result == {"summary": "", "section_summaries": []}
```

- [ ] **Step 6: Run test to verify it passes** (fallback already implemented)

Run: `uv run pytest tests/enrichment/test_client.py::test_generate_group_summary_fallback_on_error -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/agentdrive/enrichment/client.py tests/enrichment/test_client.py
git commit -m "feat(enrichment): add generate_group_summary for map phase (#27)"
```

---

### Task 2: Add reduce prompt and `generate_reduce_summary()` to EnrichmentClient

**Files:**
- Modify: `src/agentdrive/enrichment/client.py`
- Test: `tests/enrichment/test_client.py`

- [ ] **Step 1: Write failing test for `generate_reduce_summary`**

Add to `tests/enrichment/test_client.py`:

```python
@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_reduce_summary(mock_openai_cls):
    mock_client = AsyncMock()
    mock_client.chat.completions.create.return_value = _mock_chat_response(
        '{"document_summary": "Annual financial report.", "section_summaries": [{"heading": "Revenue", "summary": "Revenue grew."}]}'
    )
    mock_openai_cls.return_value = mock_client

    group_summaries = [
        {"summary": "Section covers revenue.", "section_summaries": [{"heading": "Q3 Revenue", "summary": "Revenue grew 34%."}]},
        {"summary": "Section covers expenses.", "section_summaries": [{"heading": "Operating Costs", "summary": "Costs decreased."}]},
    ]

    client = EnrichmentClient()
    result = await client.generate_reduce_summary(group_summaries)

    assert result["document_summary"] == "Annual financial report."
    assert len(result["section_summaries"]) == 1
    call_args = mock_client.chat.completions.create.call_args
    assert call_args[1]["response_format"] == {"type": "json_object"}
    content = call_args[1]["messages"][0]["content"]
    assert "Group 1" in content
    assert "Group 2" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/enrichment/test_client.py::test_generate_reduce_summary -v`
Expected: FAIL — `EnrichmentClient` has no attribute `generate_reduce_summary`

- [ ] **Step 3: Implement `generate_reduce_summary` in client.py**

Add prompt constant after `GROUP_SUMMARY_PROMPT`:

```python
REDUCE_SUMMARY_PROMPT = """Below are summaries of consecutive sections of a large document. Synthesize them into:
1. A document_summary (2-3 sentences describing the document's purpose, parties involved, and subject matter)
2. section_summaries (a merged, deduplicated list of objects with "heading" and "summary" covering the entire document)

{group_summaries_text}

Return valid JSON with this exact structure:
{{"document_summary": "...", "section_summaries": [{{"heading": "...", "summary": "..."}}]}}"""
```

Add method to `EnrichmentClient` class (after `generate_group_summary`):

```python
async def generate_reduce_summary(self, group_summaries: list[dict]) -> dict:
    """Synthesize group summaries into a final document summary (reduce phase)."""
    parts = []
    for i, group in enumerate(group_summaries, 1):
        sections_text = "\n".join(
            f"  - {s['heading']}: {s['summary']}"
            for s in group.get("section_summaries", [])
        )
        parts.append(
            f"Group {i} (of {len(group_summaries)}):\n"
            f"Summary: {group.get('summary', '')}\n"
            f"Sections:\n{sections_text}"
        )
    group_summaries_text = "\n\n".join(parts)

    try:
        response = await self._client.chat.completions.create(
            model=settings.enrichment_model,
            max_tokens=16384,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": REDUCE_SUMMARY_PROMPT.format(
                        group_summaries_text=group_summaries_text
                    ),
                }
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        return json.loads(text)
    except Exception as e:
        logger.warning(f"Reduce summary generation failed: {e}")
        return {"document_summary": "", "section_summaries": []}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/enrichment/test_client.py::test_generate_reduce_summary -v`
Expected: PASS

- [ ] **Step 5: Write failing test for error fallback**

Add to `tests/enrichment/test_client.py`:

```python
@pytest.mark.asyncio
@patch("agentdrive.enrichment.client.openai.AsyncOpenAI")
async def test_generate_reduce_summary_fallback_on_error(mock_openai_cls):
    mock_client = AsyncMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    mock_openai_cls.return_value = mock_client

    client = EnrichmentClient()
    result = await client.generate_reduce_summary([{"summary": "test", "section_summaries": []}])

    assert result == {"document_summary": "", "section_summaries": []}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/enrichment/test_client.py::test_generate_reduce_summary_fallback_on_error -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/agentdrive/enrichment/client.py tests/enrichment/test_client.py
git commit -m "feat(enrichment): add generate_reduce_summary for reduce phase (#27)"
```

---

### Task 3: Add `generate_group_summary` and `generate_reduce_summary` wrappers to contextual.py

**Files:**
- Modify: `src/agentdrive/enrichment/contextual.py`

Note: These are one-line delegation wrappers matching the existing `generate_document_summary` pattern. Existing wrappers in this file have no dedicated tests — the client methods are tested directly in `test_client.py`.

- [ ] **Step 1: Add thin wrappers**

Add after `generate_document_summary` (after line 41 in contextual.py):

```python
async def generate_group_summary(
    group_text: str, group_index: int, total_groups: int
) -> dict:
    """Summarize a group of parent chunks (map phase of hierarchical summarization)."""
    client = EnrichmentClient()
    return await client.generate_group_summary(group_text, group_index, total_groups)


async def generate_reduce_summary(group_summaries: list[dict]) -> dict:
    """Synthesize group summaries into a final document summary (reduce phase)."""
    client = EnrichmentClient()
    return await client.generate_reduce_summary(group_summaries)
```

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `uv run pytest tests/enrichment/ -v`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/agentdrive/enrichment/contextual.py
git commit -m "feat(enrichment): add group/reduce summary wrappers in contextual.py (#27)"
```

---

### Task 4: Add `_batch_parents()` helper to ingest.py

**Files:**
- Modify: `src/agentdrive/services/ingest.py`
- Create: `tests/test_summarization.py`

- [ ] **Step 1: Write failing tests for `_batch_parents`**

Create `tests/test_summarization.py`:

```python
from dataclasses import dataclass

import pytest

from agentdrive.services.ingest import _batch_parents, GROUP_BATCH_TOKENS


@dataclass
class FakeParent:
    content: str
    token_count: int


def _make_parent(tokens: int) -> FakeParent:
    """Create a fake parent with approximate content length for given token count."""
    return FakeParent(content="x " * tokens, token_count=tokens)


def test_batch_parents_single_batch():
    """All parents fit in one batch."""
    parents = [_make_parent(1000) for _ in range(3)]
    batches = _batch_parents(parents)
    assert len(batches) == 1
    assert len(batches[0]) == 3


def test_batch_parents_multiple_batches():
    """Parents split across batches at GROUP_BATCH_TOKENS boundary."""
    # 5 parents at 20k each = 100k total. Batching: [p1+p2]=40k, [p3+p4]=40k, [p5]=20k → 3 batches
    parents = [_make_parent(20_000) for _ in range(5)]
    batches = _batch_parents(parents)
    assert len(batches) == 3
    # All parents accounted for
    total = sum(len(b) for b in batches)
    assert total == 5


def test_batch_parents_oversized_single_parent():
    """A parent exceeding GROUP_BATCH_TOKENS gets its own batch."""
    parents = [
        _make_parent(60_000),  # exceeds 50k, gets own batch
        _make_parent(10_000),
        _make_parent(10_000),
    ]
    batches = _batch_parents(parents)
    assert len(batches) == 2
    assert len(batches[0]) == 1  # oversized parent alone
    assert len(batches[1]) == 2  # remaining two fit together


def test_batch_parents_empty():
    """No parents produces no batches."""
    batches = _batch_parents([])
    assert batches == []


def test_batch_parents_preserves_order():
    """Batches preserve original parent ordering."""
    parents = [_make_parent(20_000) for _ in range(4)]
    batches = _batch_parents(parents)
    flat = [p for batch in batches for p in batch]
    assert flat == parents
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_summarization.py -v`
Expected: FAIL — `_batch_parents` not found in `agentdrive.services.ingest`

- [ ] **Step 3: Implement `_batch_parents` in ingest.py**

Add constants after imports (near other module-level code). Note: `_batch_parents` uses the pre-computed `parent.token_count` attribute, not `count_tokens()` — the token counting happened during Phase 1 chunking.

```python
MAX_SINGLE_PASS_TOKENS = 200_000
GROUP_BATCH_TOKENS = 50_000
```

Add helper function before `_phase2_summarization`:

```python
def _batch_parents(parents: list) -> list[list]:
    """Group parent chunks into batches of ~GROUP_BATCH_TOKENS tokens each."""
    if not parents:
        return []
    batches: list[list] = []
    current_batch: list = []
    current_tokens = 0

    for parent in parents:
        token_count = parent.token_count
        if current_batch and current_tokens + token_count > GROUP_BATCH_TOKENS:
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0
        current_batch.append(parent)
        current_tokens += token_count

    if current_batch:
        batches.append(current_batch)
    return batches
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_summarization.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentdrive/services/ingest.py tests/test_summarization.py
git commit -m "feat(ingest): add _batch_parents helper for hierarchical summarization (#27)"
```

---

### Task 5: Add `_hierarchical_summarize()` and wire up the threshold gate

**Files:**
- Modify: `src/agentdrive/services/ingest.py`
- Modify: `tests/test_summarization.py`

- [ ] **Step 1: Write failing tests for threshold routing**

Add to `tests/test_summarization.py`:

```python
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from agentdrive.services.ingest import _phase2_summarization, MAX_SINGLE_PASS_TOKENS


def _mock_session(parents):
    """Create a mock AsyncSession that returns given parents from execute()."""
    session = MagicMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = parents
    # session.execute is async, returns result_mock
    session.execute = AsyncMock(return_value=result_mock)
    # session.add is sync (SQLAlchemy), session.commit is async
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.generate_document_summary", new_callable=AsyncMock)
async def test_phase2_small_doc_uses_single_pass(mock_gen_summary):
    """Documents under MAX_SINGLE_PASS_TOKENS use generate_document_summary directly."""
    mock_gen_summary.return_value = {
        "document_summary": "A short doc.",
        "section_summaries": [],
    }

    file = MagicMock(id=uuid4())
    parent = MagicMock(content="short text", token_count=100)
    session = _mock_session([parent])

    summary = await _phase2_summarization(file, session)

    mock_gen_summary.assert_called_once()
    assert summary.document_summary == "A short doc."


@pytest.mark.asyncio
@patch("agentdrive.services.ingest._hierarchical_summarize", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.generate_document_summary", new_callable=AsyncMock)
async def test_phase2_large_doc_uses_hierarchical(mock_gen_summary, mock_hier):
    """Documents over MAX_SINGLE_PASS_TOKENS use _hierarchical_summarize."""
    mock_hier.return_value = {
        "document_summary": "A large doc.",
        "section_summaries": [{"heading": "Intro", "summary": "Intro text."}],
    }

    file = MagicMock(id=uuid4())
    # Each parent has 50k tokens, 5 parents = 250k > 200k threshold
    parents = [MagicMock(content="x " * 1000, token_count=50_000) for _ in range(5)]
    session = _mock_session(parents)

    summary = await _phase2_summarization(file, session)

    mock_gen_summary.assert_not_called()
    mock_hier.assert_called_once()
    assert summary.document_summary == "A large doc."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_summarization.py::test_phase2_small_doc_uses_single_pass tests/test_summarization.py::test_phase2_large_doc_uses_hierarchical -v`
Expected: FAIL — `_hierarchical_summarize` not found (the token gate and function don't exist yet)

- [ ] **Step 3: Implement `_hierarchical_summarize` and modify `_phase2_summarization`**

Add imports at top of `ingest.py` (add to the existing `from agentdrive.enrichment.contextual import` block):

```python
from agentdrive.enrichment.contextual import (
    enrich_chunks_with_summaries,
    generate_document_summary,
    generate_group_summary,
    generate_reduce_summary,
)
```

Note: `enrich_chunks_with_summaries` and `generate_document_summary` are already imported — just add `generate_group_summary` and `generate_reduce_summary` to the existing import. Do NOT import `EnrichmentClient` directly — ingest.py talks to contextual.py wrappers only.

Add `_hierarchical_summarize` before `_phase2_summarization`:

```python
async def _hierarchical_summarize(parents: list) -> dict:
    """Map-reduce summarization for large documents."""
    batches = _batch_parents(parents)
    semaphore = asyncio.Semaphore(5)

    async def summarize_group(batch: list, index: int) -> dict:
        async with semaphore:
            group_text = "\n\n".join(p.content for p in batch)
            return await generate_group_summary(group_text, index, len(batches))

    group_summaries = await asyncio.gather(
        *(summarize_group(batch, i + 1) for i, batch in enumerate(batches))
    )

    return await generate_reduce_summary(list(group_summaries))
```

Modify `_phase2_summarization` to add the threshold gate. Replace lines 228-230:

```python
    # Old:
    # document_text = "\n\n".join(p.content for p in parents)
    # summary_data = await generate_document_summary(document_text)

    # New:
    total_tokens = sum(p.token_count for p in parents)

    if total_tokens > MAX_SINGLE_PASS_TOKENS:
        logger.info(
            f"File {file.id}: {total_tokens} tokens exceeds threshold, using hierarchical summarization"
        )
        summary_data = await _hierarchical_summarize(parents)
    else:
        document_text = "\n\n".join(p.content for p in parents)
        summary_data = await generate_document_summary(document_text)
```

- [ ] **Step 4: Run all summarization tests**

Run: `uv run pytest tests/test_summarization.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/agentdrive/services/ingest.py tests/test_summarization.py
git commit -m "feat(ingest): add hierarchical summarization with 200k token threshold (#27)"
```

---

### Task 6: Add end-to-end test for `_hierarchical_summarize`

**Files:**
- Modify: `tests/test_summarization.py`

The spec requires "hierarchical path tests" — a test that verifies the full map-reduce flow: batching → group summary calls → reduce call.

- [ ] **Step 1: Write failing test for `_hierarchical_summarize` end-to-end**

Add to `tests/test_summarization.py`:

```python
@pytest.mark.asyncio
@patch("agentdrive.services.ingest.generate_reduce_summary", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.generate_group_summary", new_callable=AsyncMock)
async def test_hierarchical_summarize_map_reduce_flow(mock_group, mock_reduce):
    """Verifies map phase calls generate_group_summary per batch, then reduce combines them."""
    from agentdrive.services.ingest import _hierarchical_summarize

    mock_group.side_effect = [
        {"summary": "Group 1 summary.", "section_summaries": [{"heading": "A", "summary": "a"}]},
        {"summary": "Group 2 summary.", "section_summaries": [{"heading": "B", "summary": "b"}]},
    ]
    mock_reduce.return_value = {
        "document_summary": "Full doc summary.",
        "section_summaries": [{"heading": "A", "summary": "a"}, {"heading": "B", "summary": "b"}],
    }

    # 4 parents at 30k tokens each = 120k total → 2 batches at 50k threshold
    parents = [MagicMock(content=f"content {i}", token_count=30_000) for i in range(4)]

    result = await _hierarchical_summarize(parents)

    # Map phase: 2 batches → 2 group summary calls
    assert mock_group.call_count == 2
    # Reduce phase: called once with both group summaries
    mock_reduce.assert_called_once()
    reduce_args = mock_reduce.call_args[0][0]
    assert len(reduce_args) == 2
    assert result["document_summary"] == "Full doc summary."
    assert len(result["section_summaries"]) == 2
```

- [ ] **Step 2: Run test to verify it passes** (implementation already done in Task 5)

Run: `uv run pytest tests/test_summarization.py::test_hierarchical_summarize_map_reduce_flow -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_summarization.py
git commit -m "test: add end-to-end test for hierarchical map-reduce flow (#27)"
```

---

### Task 7: Update conftest.py mocks and final verification

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add mocks for new enrichment functions**

The autouse fixture mocks enrichment functions at the ingest module level. Both `generate_group_summary` and `generate_reduce_summary` are now imported into ingest.py and need mocking for integration tests. (Integration tests use small test data that won't exceed the 200k threshold, so these mocks are a safety net, not functionally triggered.)

Add to the `mock_enrichment_and_embedding` fixture in `conftest.py` (after the existing `generate_document_summary` mock):

```python
mocker.patch(
    "agentdrive.services.ingest.generate_group_summary",
    new_callable=AsyncMock,
    return_value={"summary": "", "section_summaries": []},
)
mocker.patch(
    "agentdrive.services.ingest.generate_reduce_summary",
    new_callable=AsyncMock,
    return_value={"document_summary": "", "section_summaries": []},
)
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: mock group/reduce summary functions in conftest (#27)"
```

---

### Task 8: Final cleanup and verification

- [ ] **Step 1: Run full test suite one more time**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Verify the feature branch is clean**

Run: `git status && git log --oneline -10`
Expected: Clean working tree, all commits present
