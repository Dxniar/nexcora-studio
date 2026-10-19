"""Retain cleanup keys while a remote writer may still complete.

Revision ID: f128b628e143
Revises: 982046946361
"""
from alembic import op
import sqlalchemy as sa


revision = 'f128b628e143'
down_revision = '982046946361'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('studio_file_cleanup', sa.Column('writer_pending', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    op.drop_column('studio_file_cleanup', 'writer_pending')
