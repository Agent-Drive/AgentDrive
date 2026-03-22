import asyncio
import logging

from agentdrive.chunking.base import ParentChildChunks
from agentdrive.enrichment.client import EnrichmentClient

logger = logging.getLogger(__name__)

MAX_CONCURRENT = 5


async def enrich_chunks(
    document_text: str,
    chunk_groups: list[ParentChildChunks],
) -> list[ParentChildChunks]:
    """Enrich all chunks with LLM-generated context prefixes."""
    client = EnrichmentClient()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def enrich_one(chunk_result):
        async with semaphore:
            original_prefix = chunk_result.context_prefix
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
