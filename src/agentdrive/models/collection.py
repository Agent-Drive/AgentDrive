import uuid
from sqlalchemy import ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Collection(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "collections"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    tenant = relationship("Tenant", back_populates="collections")
    files = relationship("File", back_populates="collection")
