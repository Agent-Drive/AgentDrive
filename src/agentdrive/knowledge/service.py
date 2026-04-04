from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentdrive.knowledge.models import (
    Article,
    ArticleSource,
    KnowledgeBase,
    KnowledgeBaseFile,
)
from agentdrive.models.chunk import Chunk
from agentdrive.models.file import File
from agentdrive.models.types import ArticleStatus, ArticleType, KBStatus

logger = logging.getLogger(__name__)


class KBService:
    """CRUD operations for knowledge bases and their file associations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        tenant_id: uuid.UUID,
        name: str,
        description: str | None = None,
        config: dict | None = None,
    ) -> KnowledgeBase:
        """Create a new knowledge base. Raises ValueError if name already exists for tenant."""
        existing = await self.session.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.tenant_id == tenant_id,
                KnowledgeBase.name == name,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError(f"Knowledge base with name '{name}' already exists")

        kb = KnowledgeBase(
            tenant_id=tenant_id,
            name=name,
            description=description,
            status=KBStatus.ACTIVE,
            config=config or {},
        )
        self.session.add(kb)
        await self.session.flush()
        return kb

    async def get(
        self,
        tenant_id: uuid.UUID,
        kb_id: uuid.UUID,
    ) -> KnowledgeBase | None:
        """Get a knowledge base by tenant and ID."""
        result = await self.session.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.tenant_id == tenant_id,
                KnowledgeBase.id == kb_id,
            )
        )
        return result.scalar_one_or_none()

    async def resolve(
        self,
        tenant_id: uuid.UUID,
        name_or_id: str,
    ) -> KnowledgeBase | None:
        """Resolve a KB by UUID string or name. Returns None if not found."""
        try:
            kb_id = uuid.UUID(name_or_id)
            return await self.get(tenant_id, kb_id)
        except ValueError:
            result = await self.session.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.tenant_id == tenant_id,
                    KnowledgeBase.name == name_or_id,
                )
            )
            return result.scalar_one_or_none()

    async def list(
        self,
        tenant_id: uuid.UUID,
    ) -> list[KnowledgeBase]:
        """List all knowledge bases for a tenant, newest first."""
        result = await self.session.execute(
            select(KnowledgeBase)
            .where(KnowledgeBase.tenant_id == tenant_id)
            .order_by(KnowledgeBase.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete(
        self,
        tenant_id: uuid.UUID,
        kb_id: uuid.UUID,
    ) -> None:
        """Delete a knowledge base by tenant and ID."""
        await self.session.execute(
            delete(KnowledgeBase).where(
                KnowledgeBase.tenant_id == tenant_id,
                KnowledgeBase.id == kb_id,
            )
        )
        await self.session.flush()

    async def add_files(
        self,
        tenant_id: uuid.UUID,
        kb_id: uuid.UUID,
        file_ids: list[uuid.UUID],
    ) -> list[KnowledgeBaseFile]:
        """Add files to a KB. Validates ownership, skips duplicates."""
        kb = await self.get(tenant_id, kb_id)
        if kb is None:
            raise ValueError(f"Knowledge base {kb_id} not found")

        # Find already-linked file_ids for this KB
        existing_result = await self.session.execute(
            select(KnowledgeBaseFile.file_id).where(
                KnowledgeBaseFile.knowledge_base_id == kb_id,
                KnowledgeBaseFile.file_id.in_(file_ids),
            )
        )
        existing_file_ids = set(existing_result.scalars().all())

        added: list[KnowledgeBaseFile] = []
        for file_id in file_ids:
            if file_id in existing_file_ids:
                continue

            # Verify file exists and belongs to tenant
            file_result = await self.session.execute(
                select(File).where(
                    File.id == file_id,
                    File.tenant_id == tenant_id,
                )
            )
            if file_result.scalar_one_or_none() is None:
                raise ValueError(
                    f"File {file_id} not found or does not belong to tenant"
                )

            kbf = KnowledgeBaseFile(
                knowledge_base_id=kb_id,
                file_id=file_id,
            )
            self.session.add(kbf)
            added.append(kbf)

        await self.session.flush()
        return added

    async def remove_files(
        self,
        tenant_id: uuid.UUID,
        kb_id: uuid.UUID,
        file_ids: list[uuid.UUID],
    ) -> None:
        """Remove files from KB, clean up orphaned sources, mark affected articles stale."""
        kb = await self.get(tenant_id, kb_id)
        if kb is None:
            raise ValueError(f"Knowledge base {kb_id} not found")

        for file_id in file_ids:
            # Delete the junction record
            await self.session.execute(
                delete(KnowledgeBaseFile).where(
                    KnowledgeBaseFile.knowledge_base_id == kb_id,
                    KnowledgeBaseFile.file_id == file_id,
                )
            )

            # Find chunk IDs belonging to the removed file
            chunk_ids_result = await self.session.execute(
                select(Chunk.id).where(Chunk.file_id == file_id)
            )
            chunk_ids = list(chunk_ids_result.scalars().all())

            if not chunk_ids:
                continue

            # Find article IDs that reference these chunks (within this KB)
            affected_article_ids_result = await self.session.execute(
                select(ArticleSource.article_id)
                .distinct()
                .join(Article, Article.id == ArticleSource.article_id)
                .where(
                    ArticleSource.chunk_id.in_(chunk_ids),
                    Article.knowledge_base_id == kb_id,
                )
            )
            affected_article_ids = list(
                affected_article_ids_result.scalars().all()
            )

            # Delete orphaned ArticleSource records
            await self.session.execute(
                delete(ArticleSource).where(
                    ArticleSource.chunk_id.in_(chunk_ids),
                    ArticleSource.article_id.in_(
                        select(Article.id).where(
                            Article.knowledge_base_id == kb_id
                        )
                    ),
                )
            )

            # Mark affected articles as stale
            for article_id in affected_article_ids:
                article_result = await self.session.execute(
                    select(Article).where(Article.id == article_id)
                )
                article = article_result.scalar_one_or_none()
                if article is not None:
                    article.status = ArticleStatus.STALE

        await self.session.flush()

    async def get_file_count(self, kb_id: uuid.UUID) -> int:
        """Count files linked to a knowledge base."""
        result = await self.session.execute(
            select(func.count()).select_from(KnowledgeBaseFile).where(
                KnowledgeBaseFile.knowledge_base_id == kb_id
            )
        )
        return result.scalar_one()

    async def derive_article(
        self,
        tenant_id: uuid.UUID,
        kb_id: uuid.UUID,
        title: str,
        content: str,
        source_ids: list[uuid.UUID] | None = None,
    ) -> Article:
        """Create a derived article from Q&A or analysis output and file it into a KB."""
        kb = await self.get(tenant_id, kb_id)
        if not kb:
            raise ValueError("Knowledge base not found")

        max_tokens = (kb.config or {}).get("max_article_tokens", 8192)
        token_count = len(content.split())
        if token_count > max_tokens:
            raise ValueError(
                f"Content ({token_count} tokens) exceeds max_article_tokens ({max_tokens})"
            )

        article = Article(
            knowledge_base_id=kb_id,
            title=title,
            content=content,
            article_type=ArticleType.DERIVED,
            status=ArticleStatus.PUBLISHED,
            token_count=token_count,
        )
        self.session.add(article)
        await self.session.flush()

        if source_ids:
            for sid in source_ids:
                chunk = await self.session.get(Chunk, sid)
                if chunk:
                    source = ArticleSource(
                        article_id=article.id, chunk_id=sid, excerpt=""
                    )
                    self.session.add(source)

        await self.session.flush()
        return article

    async def get_article_count(self, kb_id: uuid.UUID) -> int:
        """Count articles in a knowledge base."""
        result = await self.session.execute(
            select(func.count()).select_from(Article).where(
                Article.knowledge_base_id == kb_id
            )
        )
        return result.scalar_one()
