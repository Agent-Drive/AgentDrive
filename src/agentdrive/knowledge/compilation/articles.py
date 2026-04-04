import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.enrichment.client import EnrichmentClient
from agentdrive.knowledge.models import Article, ArticleSource, KnowledgeBaseFile
from agentdrive.models.types import ArticleStatus, ArticleType
from agentdrive.search.engine import SearchEngine


async def generate_articles_for_concepts(
    kb_id: uuid.UUID,
    tenant_id: uuid.UUID,
    concepts: list[dict],
    session: AsyncSession,
) -> list[Article]:
    """Phase 5b: Generate articles for extracted concepts."""
    engine = SearchEngine()
    client = EnrichmentClient()
    articles: list[Article] = []

    kb_file_ids_result = await session.execute(
        select(KnowledgeBaseFile.file_id).where(
            KnowledgeBaseFile.knowledge_base_id == kb_id
        )
    )
    kb_file_ids = {row[0] for row in kb_file_ids_result.all()}

    for concept in concepts:
        name = concept["concept_name"]
        desc = concept.get("description", "")
        is_new = concept.get("is_new", True)

        results = await engine.search(
            query=f"{name}: {desc}",
            session=session,
            tenant_id=tenant_id,
            top_k=10,
            include_parent=False,
        )
        # file_id lives inside provenance dict
        relevant = [
            r
            for r in results
            if r.get("provenance", {}).get("file_id")
            and uuid.UUID(str(r["provenance"]["file_id"])) in kb_file_ids
        ]
        if not relevant:
            continue

        chunks_for_llm = [
            {"chunk_id": str(r["chunk_id"]), "content": r["content"]}
            for r in relevant[:10]
        ]
        article_data = await client.generate_article(name, desc, chunks_for_llm)
        if not article_data.get("content"):
            continue

        article = Article(
            knowledge_base_id=kb_id,
            title=article_data.get("title", name),
            content=article_data["content"],
            article_type=ArticleType.CONCEPT if is_new else ArticleType.SUMMARY,
            category=article_data.get("category"),
            status=ArticleStatus.PUBLISHED,
            token_count=len(article_data["content"].split()),
        )
        session.add(article)
        await session.flush()

        for ref in article_data.get("source_refs", []):
            try:
                chunk_uuid = uuid.UUID(ref.get("chunk_id", ""))
            except ValueError:
                continue
            source = ArticleSource(
                article_id=article.id,
                chunk_id=chunk_uuid,
                excerpt=ref.get("excerpt", ""),
            )
            session.add(source)

        articles.append(article)

    await session.flush()
    return articles
