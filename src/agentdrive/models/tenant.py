from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Tenant(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tenants"
    name: Mapped[str] = mapped_column(Text, nullable=False)
    workos_user_id: Mapped[str | None] = mapped_column(Text, unique=True)
    settings: Mapped[dict] = mapped_column(JSONB, server_default="{}")

    collections = relationship("Collection", back_populates="tenant")
    files = relationship("File", back_populates="tenant")
    api_keys = relationship("ApiKey", back_populates="tenant")
