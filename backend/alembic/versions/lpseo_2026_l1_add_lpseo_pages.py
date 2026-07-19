"""add lpseo_pages table (local-SEO programmatic pages)

Revision ID: lpseo_2026_l1
Revises: pseo_2026_p2
Create Date: 2026-07-18

"""
from alembic import op
import sqlalchemy as sa


revision = "lpseo_2026_l1"
down_revision = "pseo_2026_p2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "lpseo_pages",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("industry_label", sa.String(), nullable=False),
        sa.Column("industry_slug", sa.String(), nullable=False),
        sa.Column("city_label", sa.String(), nullable=False),
        sa.Column("city_slug", sa.String(), nullable=False),
        sa.Column("country", sa.String(), nullable=False, server_default="in"),
        sa.Column("meta_title", sa.String(), nullable=False),
        sa.Column("meta_description", sa.String(), nullable=False),
        sa.Column("h1", sa.String(), nullable=False),
        sa.Column("canonical_url", sa.String(), nullable=True),
        sa.Column("index_status", sa.String(), nullable=False, server_default="index"),
        sa.Column("quality_score", sa.Integer(), nullable=True),
        sa.Column("content", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lpseo_pages_status", "lpseo_pages", ["status"])
    op.create_index("ix_lpseo_pages_industry_city", "lpseo_pages", ["industry_slug", "city_slug"])
    op.create_index("ix_lpseo_pages_country_status", "lpseo_pages", ["country", "status"])


def downgrade():
    op.drop_index("ix_lpseo_pages_country_status", table_name="lpseo_pages")
    op.drop_index("ix_lpseo_pages_industry_city", table_name="lpseo_pages")
    op.drop_index("ix_lpseo_pages_status", table_name="lpseo_pages")
    op.drop_table("lpseo_pages")
