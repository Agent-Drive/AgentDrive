from unittest.mock import AsyncMock, patch

import pytest

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.enrichment.contextual import enrich_chunks


def make_chunk(content: str, prefix: str = "File: test.md") -> ChunkResult:
    return ChunkResult(content=content, context_prefix=prefix, token_count=10, content_type="text")


def make_group(parent_content: str, child_contents: list[str]) -> ParentChildChunks:
    parent = make_chunk(parent_content)
    children = [make_chunk(c) for c in child_contents]
    return ParentChildChunks(parent=parent, children=children)


@pytest.mark.asyncio
@patch("agentdrive.enrichment.contextual.EnrichmentClient")
async def test_enrich_replaces_context_prefix(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.generate_context.return_value = "This is enriched context."
    mock_client_cls.return_value = mock_client

    groups = [make_group("Parent text.", ["Child one.", "Child two."])]
    enriched = await enrich_chunks("Full document text.", groups)

    assert enriched[0].children[0].context_prefix == "This is enriched context."
    assert enriched[0].children[1].context_prefix == "This is enriched context."
    assert enriched[0].parent.context_prefix == "This is enriched context."


@pytest.mark.asyncio
@patch("agentdrive.enrichment.contextual.EnrichmentClient")
async def test_enrich_preserves_original_on_failure(mock_client_cls):
    mock_client = AsyncMock()
    mock_client.generate_context.return_value = ""
    mock_client_cls.return_value = mock_client

    groups = [make_group("Parent.", ["Child."])]
    groups[0].children[0].context_prefix = "Original breadcrumb"
    enriched = await enrich_chunks("Doc text.", groups)

    assert enriched[0].children[0].context_prefix == "Original breadcrumb"


@pytest.mark.asyncio
@patch("agentdrive.enrichment.contextual.EnrichmentClient")
async def test_enrich_multiple_groups(mock_client_cls):
    call_count = 0
    async def mock_generate(doc, chunk):
        nonlocal call_count
        call_count += 1
        return f"Context {call_count}"
    mock_client = AsyncMock()
    mock_client.generate_context.side_effect = mock_generate
    mock_client_cls.return_value = mock_client

    groups = [
        make_group("Parent A", ["Child A1"]),
        make_group("Parent B", ["Child B1", "Child B2"]),
    ]
    enriched = await enrich_chunks("Doc.", groups)

    # 2 parents + 3 children = 5 calls
    assert call_count == 5
