"""add description to locations

Revision ID: add_description_001
Revises: add_hours_001
Create Date: 2026-06-01

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_description_001'
down_revision = 'add_hours_001'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('locations', sa.Column('description', sa.String(), nullable=True))

def downgrade() -> None:
    op.drop_column('locations', 'description')
