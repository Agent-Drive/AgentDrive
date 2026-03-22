import cohere
from agentdrive.config import settings
from agentdrive.search.vector import SearchResult

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = cohere.Client(api_key=settings.cohere_api_key)
    return _client


def rerank_results(query: str, candidates: list[SearchResult], top_k: int = 5) -> list[SearchResult]:
    if not candidates:
        return []
    client = _get_client()
    documents = [c.content for c in candidates]
    response = client.rerank(query=query, documents=documents, model="rerank-v3.5", top_n=top_k)
    reranked = []
    for result in response.results:
        candidate = candidates[result.index]
        candidate.score = result.relevance_score
        reranked.append(candidate)
    return reranked
