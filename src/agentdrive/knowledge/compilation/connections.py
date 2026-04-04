import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.enrichment.client import EnrichmentClient
from agentdrive.knowledge.models import Article, ArticleLink
from agentdrive.models.types import LinkType

SYMMETRIC_TYPES = {LinkType.RELATED, LinkType.CONTRADICTS}


async def discover_and_link(
    kb_id: uuid.UUID, session: AsyncSession
) -> list[ArticleLink]:
    """Phase 5c-5d: Discover connections and create backlinks."""
    result = await session.execute(
        select(Article).where(Article.knowledge_base_id == kb_id)
    )
    articles = result.scalars().all()
    if len(articles) < 2:
        return []

    summaries = [{"title": a.title, "summary": a.content[:300]} for a in articles]
    title_to_id = {a.title: a.id for a in articles}

    client = EnrichmentClient()
    connections = await client.discover_connections(summaries)

    links: list[ArticleLink] = []
    for conn in connections:
        source_id = title_to_id.get(conn.get("source_title"))
        target_id = title_to_id.get(conn.get("target_title"))
        link_type_str = conn.get("link_type", "related")
        if not source_id or not target_id or source_id == target_id:
            continue
        try:
            link_type = LinkType(link_type_str)
        except ValueError:
            link_type = LinkType.RELATED

        existing = await session.execute(
            select(ArticleLink).where(
                ArticleLink.source_article_id == source_id,
                ArticleLink.target_article_id == target_id,
            )
        )
        if existing.scalar_one_or_none():
            continue

        link = ArticleLink(
            source_article_id=source_id,
            target_article_id=target_id,
            link_type=link_type,
        )
        session.add(link)
        links.append(link)

        if link_type in SYMMETRIC_TYPES:
            rev = await session.execute(
                select(ArticleLink).where(
                    ArticleLink.source_article_id == target_id,
                    ArticleLink.target_article_id == source_id,
                )
            )
            if not rev.scalar_one_or_none():
                reverse = ArticleLink(
                    source_article_id=target_id,
                    target_article_id=source_id,
                    link_type=link_type,
                )
                session.add(reverse)
                links.append(reverse)

    await session.flush()
    return links
