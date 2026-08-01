"""Partial index for the Unauthorised Changes list and its sidebar badge.

Both queries are org-wide and filter on entity_type='ProfileChange'. activity_log takes
a row from every sync, post, review and edit, so the existing (organization_id,
created_at) index made the badge count scan the org's whole recent history — on every
dashboard render, for every user. Partial, so the index stays small.

Revision ID: pc_2026_a1
Revises: ar_2026_per_loc
"""
import sqlalchemy as sa
from alembic import op

revision = "pc_2026_a1"
down_revision = "ar_2026_per_loc"
branch_labels = None
depends_on = None

INDEX_NAME = "idx_activity_log_profile_change"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "activity_log",
        # No location_id: the list's location filter is optional, and putting a column
        # the common query doesn't constrain ahead of created_at costs the ordering.
        ["organization_id", sa.text("created_at DESC")],
        unique=False,
        postgresql_where=sa.text("entity_type = 'ProfileChange'"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="activity_log")
