"""comparison: provider server_default + junction reverse indexes

Revision ID: c4e1f0a9d7b2
Revises: f718060d3dbe
Create Date: 2026-06-23

Fixes two audit findings:
- group_daily_insights.provider had only an ORM default -> raw/bulk inserts omitting
  it violated NOT NULL. Add a DB server_default.
- region_locations / custom_group_locations had no index on location_id, so reverse
  lookups ("which groups contain location X") and the locations FK cascade did seq scans.
"""
from alembic import op
import sqlalchemy as sa

revision = 'c4e1f0a9d7b2'
down_revision = 'f718060d3dbe'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('group_daily_insights', 'provider', server_default='gbp')
    op.create_index('ix_region_locations_location_id', 'region_locations', ['location_id'])
    op.create_index('ix_custom_group_locations_location_id', 'custom_group_locations', ['location_id'])


def downgrade():
    op.drop_index('ix_custom_group_locations_location_id', table_name='custom_group_locations')
    op.drop_index('ix_region_locations_location_id', table_name='region_locations')
    op.alter_column('group_daily_insights', 'provider', server_default=None)
