"""Persist one language preference shared by Telegram bot and Mini App.

Revision ID: a7c641e239df
Revises: f128b628e143
"""
from alembic import op
import sqlalchemy as sa


revision = 'a7c641e239df'
down_revision = 'f128b628e143'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('studio_users', sa.Column('language_code', sa.String(2), server_default='ru', nullable=False))


def downgrade():
    op.drop_column('studio_users', 'language_code')
