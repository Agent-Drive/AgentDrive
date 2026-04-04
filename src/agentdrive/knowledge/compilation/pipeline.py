import logging
import uuid

from sqlalchemy import text

from agentdrive.db.session import async_session_factory
from agentdrive.knowledge.compilation.articles import generate_articles_for_concepts
from agentdrive.knowledge.compilation.concepts import extract_concepts_for_kb
from agentdrive.knowledge.compilation.connections import discover_and_link
from agentdrive.knowledge.compilation.embedding import embed_articles
from agentdrive.knowledge.models import KnowledgeBase
from agentdrive.models.types import KBStatus

logger = logging.getLogger(__name__)


async def compile_kb(
    kb_id: uuid.UUID, tenant_id: uuid.UUID, force: bool = False
) -> None:
    """Run the full compilation pipeline for a KB with advisory lock."""
    lock_key = int.from_bytes(kb_id.bytes[:8], "big") & 0x7FFFFFFFFFFFFFFF

    async with async_session_factory() as session:
        await session.execute(text(f"SELECT pg_advisory_lock({lock_key})"))
        try:
            kb = await session.get(KnowledgeBase, kb_id)
            if not kb:
                logger.warning(f"KB {kb_id} not found for compilation")
                return

            kb.status = KBStatus.COMPILING
            await session.commit()

            try:
                logger.info(f"KB {kb_id}: Phase 5a - concept extraction")
                concepts = await extract_concepts_for_kb(kb_id, session)
                logger.info(f"KB {kb_id}: extracted {len(concepts)} concepts")

                if concepts:
                    logger.info(f"KB {kb_id}: Phase 5b - article generation")
                    articles = await generate_articles_for_concepts(
                        kb_id, tenant_id, concepts, session
                    )
                    logger.info(
                        f"KB {kb_id}: generated {len(articles)} articles"
                    )
                    await session.commit()

                logger.info(f"KB {kb_id}: Phase 5c-5d - connection discovery")
                links = await discover_and_link(kb_id, session)
                logger.info(f"KB {kb_id}: created {len(links)} links")
                await session.commit()

                logger.info(f"KB {kb_id}: Phase 5e - article embedding")
                embedded = await embed_articles(kb_id, session)
                logger.info(f"KB {kb_id}: embedded {embedded} articles")
                await session.commit()

                kb = await session.get(KnowledgeBase, kb_id)
                kb.status = KBStatus.ACTIVE
                await session.commit()
                logger.info(f"KB {kb_id}: compilation complete")

            except Exception as e:
                logger.exception(f"KB {kb_id}: compilation failed: {e}")
                await session.rollback()
                kb = await session.get(KnowledgeBase, kb_id)
                if kb:
                    kb.status = KBStatus.ERROR
                    await session.commit()

        finally:
            await session.execute(text(f"SELECT pg_advisory_unlock({lock_key})"))
