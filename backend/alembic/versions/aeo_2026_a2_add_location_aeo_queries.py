"""add aeo_queries to locations

Revision ID: aeo_2026_a2
Revises: aeo_2026_a1
Create Date: 2026-07-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "aeo_2026_a2"
down_revision = "aeo_2026_a1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "locations",
        sa.Column("aeo_queries", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default="[]"),
    )


def downgrade():
    op.drop_column("locations", "aeo_queries")
