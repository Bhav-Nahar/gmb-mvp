"""add_platform_device_impressions

Adds desktop/mobile × search/maps impression columns to location_daily_insights
so the Platform & Device Impressions breakdown can be persisted instead of
aggregated away at sync time.

Revision ID: a7c9e1b3d5f2
Revises: e2f3a4b5c6d7
Create Date: 2026-06-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a7c9e1b3d5f2'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None

_COLUMNS = (
    'desktop_search_impressions',
    'mobile_search_impressions',
    'desktop_maps_impressions',
    'mobile_maps_impressions',
)


def upgrade() -> None:
    with op.batch_alter_table('location_daily_insights', schema=None) as batch_op:
        for col in _COLUMNS:
            batch_op.add_column(
                sa.Column(col, sa.Integer(), nullable=False, server_default='0')
            )
    # Drop the server_default now that existing rows are backfilled to 0; the
    # ORM model supplies the default going forward.
    with op.batch_alter_table('location_daily_insights', schema=None) as batch_op:
        for col in _COLUMNS:
            batch_op.alter_column(col, server_default=None)


def downgrade() -> None:
    with op.batch_alter_table('location_daily_insights', schema=None) as batch_op:
        for col in reversed(_COLUMNS):
            batch_op.drop_column(col)
