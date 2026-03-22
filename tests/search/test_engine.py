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
    session.get = AsyncMock(return_value=None)
    tenant_id = uuid.uuid4()
    results = await engine.search("test query", session, tenant_id, top_k=5)
    assert len(results) > 0
    mock_vector.assert_called_once()
    mock_bm25.assert_called_once()
    mock_rerank.assert_called_once()
