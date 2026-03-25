"""Add file_batches, file_summaries tables and file progress fields

Revision ID: 004
Revises: 19f589d55e82
Create Date: 2026-03-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '004'
down_revision: Union[str, Sequence[str], None] = '19f589d55e82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'file_batches',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('file_id', sa.UUID(), sa.ForeignKey('files.id', ondelete='CASCADE'), nullable=False),
        sa.Column('batch_index', sa.Integer(), nullable=False),
        sa.Column('page_range', sa.Text(), nullable=True),
        sa.Column('chunking_status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('enrichment_status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('embedding_status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('chunk_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_file_batches_file_id', 'file_batches', ['file_id'])

    op.create_table(
        'file_summaries',
        sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('file_id', sa.UUID(), sa.ForeignKey('files.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('document_summary', sa.Text(), nullable=False),
        sa.Column('section_summaries', JSONB(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    op.add_column('files', sa.Column('total_batches', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('files', sa.Column('completed_batches', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('files', sa.Column('current_phase', sa.Text(), nullable=True))
    op.add_column('files', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('files', 'retry_count')
    op.drop_column('files', 'current_phase')
    op.drop_column('files', 'completed_batches')
    op.drop_column('files', 'total_batches')
    op.drop_table('file_summaries')
    op.drop_index('ix_file_batches_file_id', 'file_batches')
    op.drop_table('file_batches')
