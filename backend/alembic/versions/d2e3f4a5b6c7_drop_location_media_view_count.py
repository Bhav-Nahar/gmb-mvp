"""drop location_media.view_count

Google's Media API no longer returns per-photo view counts (the `insights`
field is absent for all items), so the column was always null. Removing it.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-06-13

"""
from alembic import op
import sqlalchemy as sa


revision = 'd2e3f4a5b6c7'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('location_media', schema=None) as batch_op:
        batch_op.drop_column('view_count')


def downgrade() -> None:
    with op.batch_alter_table('location_media', schema=None) as batch_op:
        batch_op.add_column(sa.Column('view_count', sa.Integer(), nullable=True))
