"""Add api_keys table, workos_user_id, migrate existing keys

Revision ID: 003
Revises: 002
Create Date: 2026-03-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("key_prefix", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_api_keys_prefix", "api_keys", ["key_prefix"])
    op.create_index("idx_api_keys_tenant", "api_keys", ["tenant_id"])

    op.execute("""
        INSERT INTO api_keys (tenant_id, key_prefix, key_hash, name)
        SELECT id, 'legacy__', api_key_hash, 'migrated'
        FROM tenants
        WHERE api_key_hash IS NOT NULL AND api_key_hash != ''
    """)

    op.add_column("tenants", sa.Column("workos_user_id", sa.Text()))
    op.create_index(
        "idx_tenants_workos_user",
        "tenants",
        ["workos_user_id"],
        unique=True,
        postgresql_where=sa.text("workos_user_id IS NOT NULL"),
    )

    op.drop_column("tenants", "api_key_hash")


def downgrade() -> None:
    op.add_column("tenants", sa.Column("api_key_hash", sa.Text(), nullable=True))

    op.execute("""
        UPDATE tenants SET api_key_hash = ak.key_hash
        FROM api_keys ak
        WHERE ak.tenant_id = tenants.id AND ak.key_prefix = 'legacy__'
    """)

    op.drop_index("idx_tenants_workos_user", "tenants")
    op.drop_column("tenants", "workos_user_id")
    op.drop_index("idx_api_keys_tenant", "api_keys")
    op.drop_index("idx_api_keys_prefix", "api_keys")
    op.drop_table("api_keys")
