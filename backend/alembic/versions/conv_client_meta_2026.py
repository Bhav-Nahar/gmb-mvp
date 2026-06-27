"""add conversion client ip/user-agent to organizations (Meta CAPI match keys)

Revision ID: conv_client_2026
Revises: drop_referrer_2026
Create Date: 2026-06-28

"""
from alembic import op
import sqlalchemy as sa

revision = "conv_client_2026"
down_revision = "drop_referrer_2026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("conv_client_ip", sa.String(), nullable=True))
    op.add_column("organizations", sa.Column("conv_user_agent", sa.String(), nullable=True))


def downgrade():
    op.drop_column("organizations", "conv_user_agent")
    op.drop_column("organizations", "conv_client_ip")
