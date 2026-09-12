"""Drop knowledge base and article tables."""
from alembic import op

revision: str = "008"
down_revision: str = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("article_links")
    op.drop_table("article_sources")
    op.drop_table("articles")
    op.drop_table("knowledge_base_files")
    op.drop_table("knowledge_bases")


def downgrade() -> None:
    raise NotImplementedError("No downgrade — knowledge bases are permanently removed")
