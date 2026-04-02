import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey
from agentdrive.models.types import BatchStatus


class FileBatch(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "file_batches"

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    batch_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_range: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunking_status: Mapped[str] = mapped_column(
        Text, nullable=False, default=BatchStatus.PENDING
    )
    enrichment_status: Mapped[str] = mapped_column(
        Text, nullable=False, default=BatchStatus.PENDING
    )
    embedding_status: Mapped[str] = mapped_column(
        Text, nullable=False, default=BatchStatus.PENDING
    )
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    file = relationship("File", back_populates="batches")
