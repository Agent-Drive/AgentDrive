import uuid
from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class ParentChunk(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "parent_chunks"
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("file_batches.id"), nullable=True)
    file = relationship("File", back_populates="parent_chunks")
    chunks = relationship("Chunk", back_populates="parent_chunk")
    batch = relationship("FileBatch")


class Chunk(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "chunks"
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    parent_chunk_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("parent_chunks.id"))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("file_batches.id"), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context_prefix: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    # embedding columns added via Alembic migration (pgvector types)
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    file = relationship("File", back_populates="chunks")
    parent_chunk = relationship("ParentChunk", back_populates="chunks")
    batch = relationship("FileBatch")
