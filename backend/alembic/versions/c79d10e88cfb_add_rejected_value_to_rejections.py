"""add rejected_value to rejections

Revision ID: c79d10e88cfb
Revises: 8c3b1a2d4e5f
Create Date: 2026-06-08 01:03:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c79d10e88cfb'
down_revision = '8c3b1a2d4e5f'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('gbp_location_attribute_rejections', sa.Column('rejected_value', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

def downgrade() -> None:
    op.drop_column('gbp_location_attribute_rejections', 'rejected_value')
