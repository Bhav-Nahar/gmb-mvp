"""add razorpay_plans table for durable plan-id caching

Replaces the in-process plan cache (per-process, lost on reload, not shared across
backend/worker containers) which recreated a Razorpay plan on nearly every cold
checkout — causing orphan plan sprawl and Razorpay rate-limiting.

Plans are keyed on (location_count, interval, amount_paise); the amount is part of
the key so a pricing change creates a new plan instead of reusing a stale one.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "razorpay_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_count", sa.Integer(), nullable=False),
        sa.Column("interval", sa.String(), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("razorpay_plan_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "location_count", "interval", "amount_paise",
            name="uq_razorpay_plan_count_interval_amount",
        ),
    )
    op.create_index("ix_razorpay_plans_id", "razorpay_plans", ["id"])


def downgrade():
    op.drop_index("ix_razorpay_plans_id", table_name="razorpay_plans")
    op.drop_table("razorpay_plans")
