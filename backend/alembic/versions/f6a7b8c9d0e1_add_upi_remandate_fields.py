"""add UPI re-mandate fields to organizations

Razorpay forbids changing the amount of a UPI Autopay subscription, so raising the
recurring charge after a mid-cycle location add-on needs a brand-new mandate the user
must approve. These columns track that pending state and the grace deadline after which
surplus locations are re-locked.

Revision ID: f6a7b8c9d0e1
Revises: e4f5a6b7c8d9
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "f6a7b8c9d0e1"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "organizations",
        sa.Column("subscription_payment_mode", sa.String(), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "subscription_needs_remandate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column("paid_location_quota", sa.Integer(), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("remandate_due_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("organizations", "remandate_due_at")
    op.drop_column("organizations", "paid_location_quota")
    op.drop_column("organizations", "subscription_needs_remandate")
    op.drop_column("organizations", "subscription_payment_mode")
