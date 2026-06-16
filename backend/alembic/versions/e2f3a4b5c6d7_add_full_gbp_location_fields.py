"""Add full GBP location fields (raw payload + rich fields)

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-06-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = 'e2f3a4b5c6d7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('additional_phones', JSONB(), server_default='[]', nullable=False))
        batch_op.add_column(sa.Column('special_hours', JSONB(), nullable=True))
        batch_op.add_column(sa.Column('more_hours', JSONB(), nullable=True))
        batch_op.add_column(sa.Column('service_area', JSONB(), nullable=True))
        batch_op.add_column(sa.Column('service_items', JSONB(), nullable=True))
        batch_op.add_column(sa.Column('labels', JSONB(), server_default='[]', nullable=False))
        batch_op.add_column(sa.Column('open_info', JSONB(), nullable=True))
        batch_op.add_column(sa.Column('latlng', JSONB(), nullable=True))
        batch_op.add_column(sa.Column('store_code', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('language_code', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('gbp_raw', JSONB(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.drop_column('gbp_raw')
        batch_op.drop_column('language_code')
        batch_op.drop_column('store_code')
        batch_op.drop_column('latlng')
        batch_op.drop_column('open_info')
        batch_op.drop_column('labels')
        batch_op.drop_column('service_items')
        batch_op.drop_column('service_area')
        batch_op.drop_column('more_hours')
        batch_op.drop_column('special_hours')
        batch_op.drop_column('additional_phones')
