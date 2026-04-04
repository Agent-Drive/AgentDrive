"""Knowledge base tables

Revision ID: 007
Revises: 006
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "007"
down_revision: str = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- knowledge_bases --
    op.create_table(
        "knowledge_bases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("config", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_kb_tenant_name"),
    )

    # -- knowledge_base_files (junction table) --
    op.create_table(
        "knowledge_base_files",
        sa.Column("knowledge_base_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("file_id", UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- articles --
    op.create_table(
        "articles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("knowledge_base_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("article_type", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Vector columns via raw SQL (pgvector halfvec)
    op.execute("ALTER TABLE articles ADD COLUMN embedding halfvec(256)")
    op.execute("ALTER TABLE articles ADD COLUMN embedding_full halfvec(1024)")

    # -- article_sources --
    op.create_table(
        "article_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("article_id", UUID(as_uuid=True), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", UUID(as_uuid=True), sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- article_links --
    op.create_table(
        "article_links",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_article_id", UUID(as_uuid=True), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_article_id", UUID(as_uuid=True), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("link_type", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # -- Indexes --
    op.create_index("idx_kb_tenant", "knowledge_bases", ["tenant_id"])
    op.create_index("idx_kbf_file", "knowledge_base_files", ["file_id"])
    op.create_index("idx_articles_kb", "articles", ["knowledge_base_id"])
    op.create_index("idx_articles_type", "articles", ["article_type"])
    op.create_index("idx_articles_status", "articles", ["status"])

    # HNSW index for article embeddings
    op.execute("""
        CREATE INDEX idx_articles_embedding ON articles
        USING hnsw (embedding halfvec_cosine_ops)
        WITH (m = 16, ef_construction = 128)
    """)

    # Full-text search on article content
    op.execute("""
        CREATE INDEX idx_articles_content_fts ON articles
        USING gin (to_tsvector('english', content))
    """)

    op.create_index("idx_article_sources_article", "article_sources", ["article_id"])
    op.create_index("idx_article_sources_chunk", "article_sources", ["chunk_id"])
    op.create_index("idx_article_links_source", "article_links", ["source_article_id"])
    op.create_index("idx_article_links_target", "article_links", ["target_article_id"])


def downgrade() -> None:
    op.drop_table("article_links")
    op.drop_table("article_sources")
    op.drop_table("articles")
    op.drop_table("knowledge_base_files")
    op.drop_table("knowledge_bases")
