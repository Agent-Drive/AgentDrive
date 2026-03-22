"""Add chunk_aliases table

Revision ID: 002
Revises: 001
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chunk_aliases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.execute("ALTER TABLE chunk_aliases ADD COLUMN embedding halfvec(256)")

    op.execute("""
        CREATE INDEX idx_chunk_aliases_embedding ON chunk_aliases
        USING hnsw (embedding halfvec_cosine_ops)
        WITH (m = 16, ef_construction = 128)
    """)

    op.create_index("idx_chunk_aliases_chunk", "chunk_aliases", ["chunk_id"])
    op.create_index("idx_chunk_aliases_file", "chunk_aliases", ["file_id"])


def downgrade() -> None:
    op.drop_table("chunk_aliases")
