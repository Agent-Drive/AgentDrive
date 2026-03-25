import uuid
from sqlalchemy import BigInteger, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey
from agentdrive.models.types import ContentType, FileStatus


class File(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "files"
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    collection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("collections.id"))
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    gcs_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=FileStatus.PENDING)
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    total_batches: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completed_batches: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    current_phase: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    tenant = relationship("Tenant", back_populates="files")
    collection = relationship("Collection", back_populates="files")
    chunks = relationship("Chunk", back_populates="file", cascade="all, delete-orphan")
    parent_chunks = relationship("ParentChunk", back_populates="file", cascade="all, delete-orphan")
    batches = relationship("FileBatch", back_populates="file", cascade="all, delete-orphan")
    summary = relationship("FileSummary", back_populates="file", uselist=False, cascade="all, delete-orphan")
