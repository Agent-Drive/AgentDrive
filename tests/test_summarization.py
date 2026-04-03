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
