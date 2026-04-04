import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.knowledge.models import Article
from agentdrive.models.types import ArticleStatus


async def repair_kb(
    kb_id: uuid.UUID, session: AsyncSession, apply: list[str]
) -> dict:
    actions_taken: list[str] = []

    if "stale" in apply:
        result = await session.execute(
            select(Article).where(
                Article.knowledge_base_id == kb_id,
                Article.status == ArticleStatus.STALE,
            )
        )
        stale = result.scalars().all()
        for article in stale:
            await session.delete(article)
            actions_taken.append(f"Deleted stale article: {article.title}")

    await session.flush()
    return {"actions_taken": actions_taken, "count": len(actions_taken)}
