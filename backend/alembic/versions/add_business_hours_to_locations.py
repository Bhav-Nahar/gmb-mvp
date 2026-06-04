"""add business hours to locations

Revision ID: add_hours_001
Revises: head_merge_001
Create Date: 2026-06-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_hours_001'
down_revision = '0f18c6e9db3a'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('locations', sa.Column('business_hours', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

def downgrade() -> None:
    op.drop_column('locations', 'business_hours')
