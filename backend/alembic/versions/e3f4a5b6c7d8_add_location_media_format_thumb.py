"""add media_format + thumbnail_url to location_media

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-14

"""
from alembic import op
import sqlalchemy as sa


revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('location_media', schema=None) as batch_op:
        batch_op.add_column(sa.Column('media_format', sa.String(), nullable=False, server_default='PHOTO'))
        batch_op.add_column(sa.Column('thumbnail_url', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('location_media', schema=None) as batch_op:
        batch_op.drop_column('thumbnail_url')
        batch_op.drop_column('media_format')
