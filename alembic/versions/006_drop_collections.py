"""Drop collections table and collection_id from files."""
from alembic import op

revision: str = "006"
down_revision: str = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_files_collection", table_name="files")
    op.drop_constraint("files_collection_id_fkey", table_name="files", type_="foreignkey")
    op.drop_column("files", "collection_id")
    op.drop_index("idx_collections_tenant", table_name="collections")
    op.drop_table("collections")


def downgrade() -> None:
    raise NotImplementedError("No downgrade — collections are permanently removed")
