"""add_plan_tier_to_organizations

Revision ID: f1a2b3c4d5e6
Revises: e5a8b3c1d2f4
Create Date: 2026-06-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'e5a8b3c1d2f4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('plan_tier', sa.String(), server_default='basic', nullable=False))


def downgrade() -> None:
    op.drop_column('organizations', 'plan_tier')
