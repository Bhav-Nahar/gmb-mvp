"""add lpseo_pages.index_at (drip-feed indexing schedule)

Flipping thousands of pages to index,follow on one day reads as mass generation.
`index_at` is the moment a page becomes indexable; an hourly sweep flips whatever
is due. The schedule lives here rather than in Redis because Upstash bills per
command: a sorted set of 4k members would mean per-tick range+remove churn forever,
while this is one nullable column on a row we already store, swept by a single
indexed query, and it survives a worker restart.

Revision ID: lpseo_2026_l3
Revises: lpseo_2026_l2
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa


revision = "lpseo_2026_l3"
down_revision = "lpseo_2026_l2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("lpseo_pages", sa.Column("index_at", sa.DateTime(timezone=True), nullable=True))
    # Partial-ish sweep index: the hourly task only ever asks for rows with a
    # schedule set, so a plain index on the column keeps that query cheap at 4k rows.
    op.create_index("ix_lpseo_pages_index_at", "lpseo_pages", ["index_at"])


def downgrade():
    op.drop_index("ix_lpseo_pages_index_at", table_name="lpseo_pages")
    op.drop_column("lpseo_pages", "index_at")
