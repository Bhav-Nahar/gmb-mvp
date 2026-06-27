"""drop unused organizations.referrer attribution column

Revision ID: drop_referrer_2026
Revises: merge_heads_2026
Create Date: 2026-06-28

"""
from alembic import op
import sqlalchemy as sa

revision = "drop_referrer_2026"
down_revision = "merge_heads_2026"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("organizations", "referrer")


def downgrade():
    op.add_column("organizations", sa.Column("referrer", sa.String(), nullable=True))
