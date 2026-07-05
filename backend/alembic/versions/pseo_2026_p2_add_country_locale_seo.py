"""add country + locale/SEO fields to pseo_pages

Revision ID: pseo_2026_p2
Revises: pseo_2026_p1
Create Date: 2026-07-05

"""
from alembic import op
import sqlalchemy as sa


revision = "pseo_2026_p2"
down_revision = "pseo_2026_p1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pseo_pages", sa.Column("country", sa.String(), nullable=False, server_default="in"))
    op.add_column("pseo_pages", sa.Column("canonical_url", sa.String(), nullable=True))
    op.add_column("pseo_pages", sa.Column("index_status", sa.String(), nullable=False, server_default="index"))
    op.add_column("pseo_pages", sa.Column("quality_score", sa.Integer(), nullable=True))
    op.create_index("ix_pseo_pages_country_status", "pseo_pages", ["country", "status"])


def downgrade():
    op.drop_index("ix_pseo_pages_country_status", table_name="pseo_pages")
    op.drop_column("pseo_pages", "quality_score")
    op.drop_column("pseo_pages", "index_status")
    op.drop_column("pseo_pages", "canonical_url")
    op.drop_column("pseo_pages", "country")
