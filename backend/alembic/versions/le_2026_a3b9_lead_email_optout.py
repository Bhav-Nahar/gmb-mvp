"""add lead_email_notifications opt-out flag to users

Revision ID: le_2026_a3b9
Revises: wr_2026_f2a8
Create Date: 2026-06-27

"""
from alembic import op
import sqlalchemy as sa

revision = "le_2026_a3b9"
down_revision = "wr_2026_f2a8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("lead_email_notifications", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade():
    op.drop_column("users", "lead_email_notifications")
