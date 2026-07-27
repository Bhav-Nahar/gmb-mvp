"""competitor lat/lng

Revision ID: d1a2b3c4e5f6
Revises: c5845d6b9b2c
Create Date: 2026-07-28

"""
from alembic import op
import sqlalchemy as sa

revision = 'd1a2b3c4e5f6'
down_revision = 'c5845d6b9b2c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tracked_competitors', sa.Column('lat', sa.Float(), nullable=True))
    op.add_column('tracked_competitors', sa.Column('lng', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('tracked_competitors', 'lng')
    op.drop_column('tracked_competitors', 'lat')
