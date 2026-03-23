import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class ApiKey(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "api_keys"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    key_prefix: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tenant = relationship("Tenant", back_populates="api_keys")
