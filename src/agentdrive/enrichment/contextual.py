import asyncio
import logging

from agentdrive.chunking.base import ParentChildChunks
from agentdrive.enrichment.client import EnrichmentClient

logger = logging.getLogger(__name__)

MAX_CONCURRENT = 5
NEIGHBOR_RANGE = 3


async def enrich_chunks(
    document_text: str,
    chunk_groups: list[ParentChildChunks],
) -> list[ParentChildChunks]:
    """Enrich all chunks with LLM-generated context prefixes (legacy full-doc approach)."""
    client = EnrichmentClient()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def enrich_one(chunk_result):
        async with semaphore:
            context = await client.generate_context(document_text, chunk_result.content)
            if context:
                chunk_result.context_prefix = context
            # If empty (failure), keep original breadcrumb

    tasks = []
    for group in chunk_groups:
        tasks.append(enrich_one(group.parent))
        for child in group.children:
            tasks.append(enrich_one(child))

    await asyncio.gather(*tasks)
    return chunk_groups


async def generate_document_summary(document_text: str) -> dict:
    """Generate a document summary and section summaries (pass 1 of two-pass enrichment)."""
    client = EnrichmentClient()
    return await client.generate_summary(document_text)


def _find_section_summary(
    chunk_content: str, section_summaries: list[dict]
) -> str:
    """Find the relevant section summary for a chunk.

    TODO: Implement proper section matching based on chunk position or heading detection.
    For now, returns all section summaries concatenated.
    """
    if not section_summaries:
        return ""
    return " | ".join(
        f"{s['heading']}: {s['summary']}" for s in section_summaries
    )


def _get_neighbors(
    chunk_groups: list[ParentChildChunks], group_index: int
) -> str:
    """Return content from ±NEIGHBOR_RANGE parent chunks, truncated to 500 chars each."""
    start = max(0, group_index - NEIGHBOR_RANGE)
    end = min(len(chunk_groups), group_index + NEIGHBOR_RANGE + 1)
    parts = []
    for i in range(start, end):
        if i == group_index:
            continue
        content = chunk_groups[i].parent.content[:500]
        parts.append(content)
    return "\n---\n".join(parts)


async def enrich_chunks_with_summaries(
    chunk_groups: list[ParentChildChunks],
    doc_summary: str,
    section_summaries: list[dict],
) -> list[ParentChildChunks]:
    """Enrich chunks using document summary + local context (pass 2 of two-pass enrichment)."""
    client = EnrichmentClient()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def enrich_one(chunk_result, group_index: int):
        async with semaphore:
            section_ctx = _find_section_summary(
                chunk_result.content, section_summaries
            )
            neighbors = _get_neighbors(chunk_groups, group_index)
            context = await client.generate_context_with_summary(
                doc_summary=doc_summary,
                section_summary=section_ctx,
                neighbors=neighbors,
                chunk_text=chunk_result.content,
            )
            if context:
                chunk_result.context_prefix = context
            # If empty (failure), keep original prefix

    tasks = []
    for idx, group in enumerate(chunk_groups):
        tasks.append(enrich_one(group.parent, idx))
        for child in group.children:
            tasks.append(enrich_one(child, idx))

    await asyncio.gather(*tasks)
    return chunk_groups
