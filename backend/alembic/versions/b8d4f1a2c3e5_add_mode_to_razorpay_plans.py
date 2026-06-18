"""add mode to razorpay_plans and widen unique constraint

The plan cache was keyed on (location_count, interval, amount_paise) only. After
introducing test/live mode prefixing on cached Razorpay ids, the first row cached
in test mode blocked the live row for the same tier from ever persisting (unique
violation -> rollback), so live checkouts recreated a fresh Razorpay plan every
time — reintroducing the plan sprawl and 429 rate-limiting the cache exists to
prevent. Add a `mode` column and include it in the unique key so a test-mode and a
live-mode plan for the same tier can coexist.

Existing rows are backfilled from the `mode:` prefix on razorpay_plan_id; legacy
unprefixed rows default to 'live' (the production mode).

Revision ID: b8d4f1a2c3e5
Revises: a7c9e1b3d5f2
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = "b8d4f1a2c3e5"
down_revision = "a7c9e1b3d5f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "razorpay_plans",
        sa.Column("mode", sa.String(), nullable=True),
    )
    # Backfill from the mode prefix on the cached id; legacy unprefixed rows -> 'live'.
    op.execute(
        """
        UPDATE razorpay_plans
        SET mode = CASE
            WHEN razorpay_plan_id LIKE 'test:%' THEN 'test'
            WHEN razorpay_plan_id LIKE 'live:%' THEN 'live'
            ELSE 'live'
        END
        WHERE mode IS NULL
        """
    )
    op.alter_column("razorpay_plans", "mode", nullable=False)

    op.drop_constraint(
        "uq_razorpay_plan_count_interval_amount",
        "razorpay_plans",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_razorpay_plan_count_interval_amount_mode",
        "razorpay_plans",
        ["location_count", "interval", "amount_paise", "mode"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_razorpay_plan_count_interval_amount_mode",
        "razorpay_plans",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_razorpay_plan_count_interval_amount",
        "razorpay_plans",
        ["location_count", "interval", "amount_paise"],
    )
    op.drop_column("razorpay_plans", "mode")
