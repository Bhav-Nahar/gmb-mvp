"""add aeo_auto_enabled to locations

Revision ID: aeo_2026_a3
Revises: aeo_2026_a2
Create Date: 2026-07-04

"""
from alembic import op
import sqlalchemy as sa


revision = "aeo_2026_a3"
down_revision = "aeo_2026_a2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "locations",
        sa.Column("aeo_auto_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade():
    op.drop_column("locations", "aeo_auto_enabled")
