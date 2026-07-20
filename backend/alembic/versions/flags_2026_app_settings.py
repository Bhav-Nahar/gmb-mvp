"""add app_settings key-value table for runtime feature flags

Revision ID: flags_2026_kv
Revises: lpseo_2026_l1
Create Date: 2026-07-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'flags_2026_kv'
down_revision = 'lpseo_2026_l1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(), primary_key=True),
        sa.Column('value', sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('app_settings')
