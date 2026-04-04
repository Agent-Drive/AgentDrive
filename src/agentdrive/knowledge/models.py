import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey
from agentdrive.models.types import ArticleStatus, KBStatus


class KnowledgeBase(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "knowledge_bases"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=KBStatus.ACTIVE)
    config: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    tenant = relationship("Tenant")
    articles = relationship("Article", back_populates="knowledge_base", cascade="all, delete-orphan")
    kb_files = relationship("KnowledgeBaseFile", back_populates="knowledge_base", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_kb_tenant_name"),
    )


class KnowledgeBaseFile(Base):
    __tablename__ = "knowledge_base_files"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    knowledge_base = relationship("KnowledgeBase", back_populates="kb_files")
    file = relationship("File")


class Article(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "articles"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    article_type: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=ArticleStatus.DRAFT)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # NOTE: embedding halfvec(256) and embedding_full halfvec(1024) added via Alembic migration, not ORM

    knowledge_base = relationship("KnowledgeBase", back_populates="articles")
    sources = relationship("ArticleSource", back_populates="article", cascade="all, delete-orphan")
    outgoing_links = relationship(
        "ArticleLink", foreign_keys="ArticleLink.source_article_id",
        back_populates="source_article", cascade="all, delete-orphan",
    )
    incoming_links = relationship(
        "ArticleLink", foreign_keys="ArticleLink.target_article_id",
        back_populates="target_article", cascade="all, delete-orphan",
    )


class ArticleSource(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "article_sources"

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
    )
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)

    article = relationship("Article", back_populates="sources")
    chunk = relationship("Chunk")


class ArticleLink(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "article_links"

    source_article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    target_article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    link_type: Mapped[str] = mapped_column(Text, nullable=False)

    source_article = relationship("Article", foreign_keys=[source_article_id], back_populates="outgoing_links")
    target_article = relationship("Article", foreign_keys=[target_article_id], back_populates="incoming_links")
