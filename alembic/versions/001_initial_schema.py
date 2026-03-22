"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("api_key_hash", sa.Text(), nullable=False),
        sa.Column("settings", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "collections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name"),
    )

    op.create_table(
        "files",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("collection_id", UUID(as_uuid=True), sa.ForeignKey("collections.id")),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("gcs_path", sa.Text(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "parent_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("file_id", UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("file_id", UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_chunk_id", UUID(as_uuid=True), sa.ForeignKey("parent_chunks.id")),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("context_prefix", sa.Text(), nullable=False, server_default=""),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Vector columns (pgvector halfvec)
    op.execute("ALTER TABLE chunks ADD COLUMN embedding halfvec(256)")
    op.execute("ALTER TABLE chunks ADD COLUMN embedding_full halfvec(1024)")

    # HNSW indexes — separate for docs and code (different embedding spaces)
    op.execute("""
        CREATE INDEX idx_chunks_embedding_docs ON chunks
        USING hnsw (embedding halfvec_cosine_ops)
        WITH (m = 16, ef_construction = 128)
        WHERE content_type != 'code'
    """)
    op.execute("""
        CREATE INDEX idx_chunks_embedding_code ON chunks
        USING hnsw (embedding halfvec_cosine_ops)
        WITH (m = 16, ef_construction = 128)
        WHERE content_type = 'code'
    """)

    # Full-text search index
    op.execute("""
        CREATE INDEX idx_chunks_content_fts ON chunks
        USING gin (to_tsvector('english', content))
    """)

    # Foreign key indexes
    op.create_index("idx_files_tenant", "files", ["tenant_id"])
    op.create_index("idx_files_collection", "files", ["collection_id"])
    op.create_index("idx_collections_tenant", "collections", ["tenant_id"])
    op.create_index("idx_chunks_file", "chunks", ["file_id"])


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("parent_chunks")
    op.drop_table("files")
    op.drop_table("collections")
    op.drop_table("tenants")
