import uuid
from agentdrive.search.fusion import reciprocal_rank_fusion
from agentdrive.search.vector import SearchResult

def make_result(chunk_id: str, score: float) -> SearchResult:
    return SearchResult(
        chunk_id=uuid.UUID(chunk_id), file_id=uuid.uuid4(),
        content="test", context_prefix="", token_count=10,
        content_type="text", score=score, metadata={},
    )

ID_A = "00000000-0000-0000-0000-000000000001"
ID_B = "00000000-0000-0000-0000-000000000002"
ID_C = "00000000-0000-0000-0000-000000000003"

def test_rrf_merges_two_lists():
    list_a = [make_result(ID_A, 0.9), make_result(ID_B, 0.8)]
    list_b = [make_result(ID_B, 0.95), make_result(ID_C, 0.7)]
    merged = reciprocal_rank_fusion([list_a, list_b], k=60, top_k=10)
    ids = [r.chunk_id for r in merged]
    assert uuid.UUID(ID_B) in ids

def test_rrf_respects_top_k():
    results = [make_result(f"00000000-0000-0000-0000-{i:012d}", 0.5) for i in range(1, 20)]
    merged = reciprocal_rank_fusion([results], k=60, top_k=5)
    assert len(merged) <= 5

def test_rrf_empty_lists():
    merged = reciprocal_rank_fusion([[], []], k=60, top_k=10)
    assert merged == []
