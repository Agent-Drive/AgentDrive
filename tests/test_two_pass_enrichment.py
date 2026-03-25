import pytest
from unittest.mock import AsyncMock, patch

from agentdrive.chunking.base import ChunkResult, ParentChildChunks
from agentdrive.enrichment.contextual import (
    generate_document_summary,
    enrich_chunks_with_summaries,
)


@pytest.mark.asyncio
async def test_generate_document_summary():
    with patch("agentdrive.enrichment.contextual.EnrichmentClient") as MockClient:
        instance = MockClient.return_value
        instance.generate_summary = AsyncMock(
            return_value={
                "document_summary": "A contract between Acme and Beta Corp.",
                "section_summaries": [
                    {"heading": "Liability", "summary": "Caps liability at $5M"}
                ],
            }
        )
        result = await generate_document_summary("Full document text here...")
        assert result["document_summary"] == "A contract between Acme and Beta Corp."
        assert len(result["section_summaries"]) == 1


@pytest.mark.asyncio
async def test_enrich_chunks_with_summaries():
    chunk_groups = [
        ParentChildChunks(
            parent=ChunkResult(
                content="Section about pricing",
                context_prefix="",
                token_count=10,
                content_type="text",
            ),
            children=[
                ChunkResult(
                    content="Widget costs $50",
                    context_prefix="",
                    token_count=5,
                    content_type="text",
                )
            ],
        ),
        ParentChildChunks(
            parent=ChunkResult(
                content="Section about delivery",
                context_prefix="",
                token_count=10,
                content_type="text",
            ),
            children=[
                ChunkResult(
                    content="Ships in 3 days",
                    context_prefix="",
                    token_count=5,
                    content_type="text",
                )
            ],
        ),
    ]

    with patch("agentdrive.enrichment.contextual.EnrichmentClient") as MockClient:
        instance = MockClient.return_value
        instance.generate_context_with_summary = AsyncMock(
            return_value="Enriched prefix"
        )
        result = await enrich_chunks_with_summaries(
            chunk_groups,
            "A product catalog for Acme Corp widgets.",
            [{"heading": "Pricing", "summary": "Widget pricing details"}],
        )
        for group in result:
            assert group.parent.context_prefix == "Enriched prefix"
            for child in group.children:
                assert child.context_prefix == "Enriched prefix"


@pytest.mark.asyncio
async def test_enrich_chunks_with_summaries_preserves_on_failure():
    """When enrichment returns empty string, keep original prefix."""
    chunk_groups = [
        ParentChildChunks(
            parent=ChunkResult(
                content="Parent content",
                context_prefix="Original breadcrumb",
                token_count=10,
                content_type="text",
            ),
            children=[
                ChunkResult(
                    content="Child content",
                    context_prefix="Original child breadcrumb",
                    token_count=5,
                    content_type="text",
                )
            ],
        ),
    ]

    with patch("agentdrive.enrichment.contextual.EnrichmentClient") as MockClient:
        instance = MockClient.return_value
        instance.generate_context_with_summary = AsyncMock(return_value="")
        result = await enrich_chunks_with_summaries(
            chunk_groups,
            "Doc summary.",
            [],
        )
        assert result[0].parent.context_prefix == "Original breadcrumb"
        assert result[0].children[0].context_prefix == "Original child breadcrumb"
