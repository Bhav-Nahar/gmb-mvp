"""merge heads

Revision ID: merge_heads_2026
Revises: attr_2026_a1f2, le_2026_a3b9
Create Date: 2026-06-27 22:38:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'merge_heads_2026'
down_revision = ('attr_2026_a1f2', 'le_2026_a3b9')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
