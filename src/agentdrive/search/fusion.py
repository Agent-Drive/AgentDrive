from agentdrive.search.vector import SearchResult

def reciprocal_rank_fusion(
    result_lists: list[list[SearchResult]], k: int = 60, top_k: int = 20,
) -> list[SearchResult]:
    scores: dict[str, float] = {}
    result_map: dict[str, SearchResult] = {}

    for results in result_lists:
        for rank, result in enumerate(results):
            key = str(result.chunk_id)
            rrf_score = 1.0 / (k + rank + 1)
            scores[key] = scores.get(key, 0.0) + rrf_score
            if key not in result_map:
                result_map[key] = result

    sorted_keys = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    merged = []
    for key in sorted_keys[:top_k]:
        result = result_map[key]
        result.score = scores[key]
        merged.append(result)

    return merged
