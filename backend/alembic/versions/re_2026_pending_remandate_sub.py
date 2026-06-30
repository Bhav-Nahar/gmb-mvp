"""track the pending UPI re-mandate subscription id

A re-mandate creates a brand-new subscription the user must approve. Without
remembering which one is pending, a repeated /remandate call (double click, retry)
created a SECOND authenticated mandate that kept billing the customer alongside the
first. This column lets us reuse an outstanding pending mandate and cancel a stale
one instead of stacking duplicates.

Revision ID: re_2026_pending_remandate
Revises: ar_2026_auto_reply
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "re_2026_pending_remandate"
down_revision = "ar_2026_auto_reply"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "organizations",
        sa.Column("pending_remandate_subscription_id", sa.String(), nullable=True),
    )


def downgrade():
    op.drop_column("organizations", "pending_remandate_subscription_id")
