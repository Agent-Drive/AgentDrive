from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from agentdrive.models.base import Base, TimestampMixin, UUIDPrimaryKey


class Tenant(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tenants"
    name: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_hash: Mapped[str] = mapped_column(Text, nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    collections = relationship("Collection", back_populates="tenant")
    files = relationship("File", back_populates="tenant")
