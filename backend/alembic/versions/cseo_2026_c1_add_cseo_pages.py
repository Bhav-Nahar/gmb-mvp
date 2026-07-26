"""add cseo_pages table (country pillar for the Local SEO universe)

One row per market, served at /{locale}/local-seo-services/. Unique on country
rather than slug: the slug segment is the same constant in every market.

Revision ID: cseo_2026_c1
Revises: lpseo_2026_l3
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa


revision = "cseo_2026_c1"
down_revision = "lpseo_2026_l3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cseo_pages",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("country", sa.String(), nullable=False, unique=True),
        sa.Column("country_label", sa.String(), nullable=False),
        sa.Column("meta_title", sa.String(), nullable=False),
        sa.Column("meta_description", sa.String(), nullable=False),
        sa.Column("h1", sa.String(), nullable=False),
        sa.Column("canonical_url", sa.String(), nullable=True),
        sa.Column("index_status", sa.String(), nullable=False, server_default="noindex"),
        sa.Column("quality_score", sa.Integer(), nullable=True),
        sa.Column("content", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cseo_pages_status", "cseo_pages", ["status"])


def downgrade():
    op.drop_index("ix_cseo_pages_status", table_name="cseo_pages")
    op.drop_table("cseo_pages")
