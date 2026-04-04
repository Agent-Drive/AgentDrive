import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.knowledge.models import Article, ArticleLink, ArticleSource
from agentdrive.models.types import ArticleStatus


async def run_health_check(
    kb_id: uuid.UUID, session: AsyncSession, quick: bool = False
) -> dict:
    result = await session.execute(
        select(Article).where(Article.knowledge_base_id == kb_id)
    )
    articles = result.scalars().all()
    total = len(articles)
    if total == 0:
        return {"score": 1.0, "issues": [], "suggestions": []}

    issues: list[dict] = []
    suggestions: list[dict] = []
    articles_with_issues: set[uuid.UUID] = set()

    # Check 1: Coverage — compiled articles with no sources
    for article in articles:
        if article.article_type in ("derived", "manual"):
            continue
        source_count = await session.execute(
            select(func.count())
            .select_from(ArticleSource)
            .where(ArticleSource.article_id == article.id)
        )
        if (source_count.scalar() or 0) == 0:
            issues.append(
                {
                    "type": "no_sources",
                    "article_id": str(article.id),
                    "reason": f"Article '{article.title}' has no source references",
                }
            )
            articles_with_issues.add(article.id)

    # Check 2: Staleness
    for article in articles:
        if article.status == ArticleStatus.STALE:
            issues.append(
                {
                    "type": "stale",
                    "article_id": str(article.id),
                    "reason": f"Article '{article.title}' is marked stale",
                }
            )
            suggestions.append(
                {"action": "recompile", "article_ids": [str(article.id)]}
            )
            articles_with_issues.add(article.id)

    # Check 3: Orphan detection (only if >1 article)
    if total > 1:
        for article in articles:
            link_count = await session.execute(
                select(func.count())
                .select_from(ArticleLink)
                .where(
                    (ArticleLink.source_article_id == article.id)
                    | (ArticleLink.target_article_id == article.id)
                )
            )
            if (link_count.scalar() or 0) == 0:
                issues.append(
                    {
                        "type": "orphan",
                        "article_id": str(article.id),
                        "reason": f"Article '{article.title}' has no links to other articles",
                    }
                )
                suggestions.append(
                    {"action": "link", "source": str(article.id)}
                )
                articles_with_issues.add(article.id)

    # Expensive checks skipped in quick mode — TODO for future

    healthy = total - len(articles_with_issues)
    score = healthy / total if total > 0 else 1.0

    return {
        "score": round(score, 2),
        "issues": issues,
        "suggestions": suggestions,
    }
