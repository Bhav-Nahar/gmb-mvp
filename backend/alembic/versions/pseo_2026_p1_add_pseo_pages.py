"""add pseo_pages table

Revision ID: pseo_2026_p1
Revises: aeo_2026_a3
Create Date: 2026-07-05

"""
from alembic import op
import sqlalchemy as sa


revision = "pseo_2026_p1"
down_revision = "aeo_2026_a3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pseo_pages",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("industry_label", sa.String(), nullable=False),
        sa.Column("industry_slug", sa.String(), nullable=False),
        sa.Column("city_label", sa.String(), nullable=False),
        sa.Column("city_slug", sa.String(), nullable=False),
        sa.Column("meta_title", sa.String(), nullable=False),
        sa.Column("meta_description", sa.String(), nullable=False),
        sa.Column("h1", sa.String(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pseo_pages_status", "pseo_pages", ["status"])
    op.create_index("ix_pseo_pages_industry_city", "pseo_pages", ["industry_slug", "city_slug"])


def downgrade():
    op.drop_index("ix_pseo_pages_industry_city", table_name="pseo_pages")
    op.drop_index("ix_pseo_pages_status", table_name="pseo_pages")
    op.drop_table("pseo_pages")
