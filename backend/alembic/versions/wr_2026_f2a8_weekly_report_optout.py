"""add weekly_report_email opt-out flag to users

Revision ID: wr_2026_f2a8
Revises: cmp_idx_2026_e1f4
Create Date: 2026-06-27

"""
from alembic import op
import sqlalchemy as sa

revision = "wr_2026_f2a8"
down_revision = "cmp_idx_2026_e1f4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("weekly_report_email", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade():
    op.drop_column("users", "weekly_report_email")
