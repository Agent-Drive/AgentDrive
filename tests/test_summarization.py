from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agentdrive.services.ingest import (
    _batch_parents,
    _hierarchical_summarize,
    _phase2_summarization,
    GROUP_BATCH_TOKENS,
    MAX_SINGLE_PASS_TOKENS,
)


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
    # 5 parents at 20k each = 100k total. Batching: [p1+p2]=40k, [p3+p4]=40k, [p5]=20k -> 3 batches
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


@pytest.mark.asyncio
@patch("agentdrive.services.ingest.generate_reduce_summary", new_callable=AsyncMock)
@patch("agentdrive.services.ingest.generate_group_summary", new_callable=AsyncMock)
async def test_hierarchical_summarize_map_reduce_flow(mock_group, mock_reduce):
    """Verifies map phase calls generate_group_summary per batch, then reduce combines them."""
    mock_group.side_effect = [
        {"summary": "Group 1 summary.", "section_summaries": [{"heading": "A", "summary": "a"}]},
        {"summary": "Group 2 summary.", "section_summaries": [{"heading": "B", "summary": "b"}]},
    ]
    mock_reduce.return_value = {
        "document_summary": "Full doc summary.",
        "section_summaries": [{"heading": "A", "summary": "a"}, {"heading": "B", "summary": "b"}],
    }

    # 4 parents at 20k tokens each = 80k total → 2 batches of 2 at 50k threshold
    parents = [MagicMock(content=f"content {i}", token_count=20_000) for i in range(4)]

    result = await _hierarchical_summarize(parents)

    # Map phase: 2 batches → 2 group summary calls
    assert mock_group.call_count == 2
    # Reduce phase: called once with both group summaries
    mock_reduce.assert_called_once()
    reduce_args = mock_reduce.call_args[0][0]
    assert len(reduce_args) == 2
    assert result["document_summary"] == "Full doc summary."
    assert len(result["section_summaries"]) == 2
