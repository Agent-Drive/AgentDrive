import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class FileSummary(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "file_summaries"

    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    document_summary: Mapped[str] = mapped_column(Text, nullable=False)
    section_summaries: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")

    file = relationship("File", back_populates="summary")
