"""add lpseo_pages.page_type (leaf / industry_pillar / city_pillar)

Everything under /{locale}/local-seo-services/{slug} shares this table: the
industry x city leaves, plus the industry and city pillars. They differ by
template, not by storage, so the discriminator belongs in a column rather than
buried in the content JSON.

It is not cosmetic. The drip-feed scheduler selects on
(status=published, index_status=noindex, quality_score>=gate) with no notion of
type, so once pillars share the table, arming the drip would sweep them into the
20-30/day trickle meant for generated leaves. Pillars go live deliberately, one
at a time. This column is what lets the scheduler say "leaves only".

Revision ID: lpseo_2026_l4
Revises: cseo_2026_c1
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa


revision = "lpseo_2026_l4"
down_revision = "cseo_2026_c1"
branch_labels = None
depends_on = None


def upgrade():
    # Existing rows are all leaves, so the server default backfills them correctly.
    op.add_column("lpseo_pages", sa.Column("page_type", sa.String(), nullable=False,
                                           server_default="leaf"))
    op.create_index("ix_lpseo_pages_page_type", "lpseo_pages", ["page_type"])


def downgrade():
    op.drop_index("ix_lpseo_pages_page_type", table_name="lpseo_pages")
    op.drop_column("lpseo_pages", "page_type")
