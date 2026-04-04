import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey
from agentdrive.models.types import KBStatus


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
