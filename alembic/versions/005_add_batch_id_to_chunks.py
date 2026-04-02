"""Add batch_id FK to chunks and parent_chunks

Revision ID: 005
Revises: 004
Create Date: 2026-03-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '005'
down_revision: Union[str, Sequence[str], None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('parent_chunks', sa.Column('batch_id', sa.UUID(), sa.ForeignKey('file_batches.id'), nullable=True))
    op.add_column('chunks', sa.Column('batch_id', sa.UUID(), sa.ForeignKey('file_batches.id'), nullable=True))
    op.create_index('ix_parent_chunks_batch_id', 'parent_chunks', ['batch_id'])
    op.create_index('ix_chunks_batch_id', 'chunks', ['batch_id'])


def downgrade() -> None:
    op.drop_index('ix_chunks_batch_id', 'chunks')
    op.drop_index('ix_parent_chunks_batch_id', 'parent_chunks')
    op.drop_column('chunks', 'batch_id')
    op.drop_column('parent_chunks', 'batch_id')
