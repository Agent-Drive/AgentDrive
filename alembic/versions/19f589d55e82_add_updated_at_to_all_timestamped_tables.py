"""add updated_at to all timestamped tables

Revision ID: 19f589d55e82
Revises: 003
Create Date: 2026-03-24 12:57:55.721306

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19f589d55e82'
down_revision: Union[str, Sequence[str], None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add updated_at column to all tables using TimestampMixin."""
    for table in ('tenants', 'files', 'chunks', 'parent_chunks', 'collections', 'chunk_aliases', 'api_keys'):
        op.add_column(table, sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ))


def downgrade() -> None:
    """Remove updated_at column from all tables using TimestampMixin."""
    for table in ('api_keys', 'chunk_aliases', 'collections', 'parent_chunks', 'chunks', 'files', 'tenants'):
        op.drop_column(table, 'updated_at')
