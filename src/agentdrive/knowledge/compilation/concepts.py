import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.enrichment.client import EnrichmentClient
from agentdrive.knowledge.models import Article, KnowledgeBaseFile
from agentdrive.models.file_summary import FileSummary


async def extract_concepts_for_kb(
    kb_id: uuid.UUID, session: AsyncSession
) -> list[dict]:
    """Phase 5a: Extract concepts from KB file summaries."""
    kb_files = await session.execute(
        select(KnowledgeBaseFile.file_id).where(
            KnowledgeBaseFile.knowledge_base_id == kb_id
        )
    )
    file_ids = [row[0] for row in kb_files.all()]
    if not file_ids:
        return []

    summaries_result = await session.execute(
        select(FileSummary).where(FileSummary.file_id.in_(file_ids))
    )
    summaries = summaries_result.scalars().all()

    summaries_text = "\n\n".join(
        f"Document: {s.document_summary}\nSections: "
        + "; ".join(
            f"{sec['heading']}: {sec['summary']}"
            for sec in (s.section_summaries or [])
        )
        for s in summaries
    )

    existing = await session.execute(
        select(Article.title).where(Article.knowledge_base_id == kb_id)
    )
    existing_titles = [row[0] for row in existing.all()]

    client = EnrichmentClient()
    return await client.extract_concepts(summaries_text, existing_titles)
