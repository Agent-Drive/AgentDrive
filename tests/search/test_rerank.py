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


@patch("agentdrive.search.rerank._get_client")
def test_rerank_reorders(mock_get_client):
    mock_client = MagicMock()
    mock_client.rerank.return_value = MagicMock(
        results=[
            MagicMock(index=1, relevance_score=0.95),
            MagicMock(index=0, relevance_score=0.80),
        ]
    )
    mock_get_client.return_value = mock_client
    candidates = [make_result("less relevant", 0.9), make_result("more relevant", 0.8)]
    reranked = rerank_results("test query", candidates, top_k=2)
    assert len(reranked) == 2
    assert reranked[0].content == "more relevant"
    assert reranked[0].score == 0.95


@patch("agentdrive.search.rerank._get_client")
def test_rerank_respects_top_k(mock_get_client):
    mock_client = MagicMock()
    mock_client.rerank.return_value = MagicMock(
        results=[MagicMock(index=0, relevance_score=0.9)]
    )
    mock_get_client.return_value = mock_client
    candidates = [make_result("a", 0.5), make_result("b", 0.4)]
    reranked = rerank_results("query", candidates, top_k=1)
    assert len(reranked) == 1


def test_rerank_empty_candidates():
    result = rerank_results("query", [], top_k=5)
    assert result == []
