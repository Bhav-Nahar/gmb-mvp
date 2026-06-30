"""partial indexes for the billing lifecycle sweeps

The trial-expiry, grace-lapse, re-mandate and reconcile sweeps filter
`organizations` on columns that have no supporting index, so each runs a full
table scan every cycle (6h / 30m). At 100k orgs that is the dominant DB cost.
Add partial indexes matching each sweep's predicate. Built CONCURRENTLY so the
index creation never takes a write lock on `organizations` under live traffic.

Revision ID: idx_2026_billing_sweeps
Revises: re_2026_pending_remandate
Create Date: 2026-07-01
"""
from alembic import op

revision = "idx_2026_billing_sweeps"
down_revision = "re_2026_pending_remandate"
branch_labels = None
depends_on = None

# (name, column, partial predicate). Partial so the index only covers rows a sweep
# actually scans, keeping it tiny relative to the table.
_INDEXES = [
    ("ix_org_trial_due", "trial_ends_at", "subscription_status = 'trial'"),
    ("ix_org_grace_due", "grace_period_ends_at", "subscription_status = 'past_due'"),
    ("ix_org_active_cycle", "billing_cycle", "subscription_status = 'active'"),
    ("ix_org_remandate_due", "remandate_due_at", "subscription_needs_remandate"),
    ("ix_org_sub_id", "razorpay_subscription_id", "razorpay_subscription_id IS NOT NULL"),
]


def upgrade():
    bind = op.get_bind()
    # CONCURRENTLY is Postgres-only and cannot run inside a transaction; on SQLite
    # (tests) the table is fresh and tiny, so skip entirely.
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for name, col, predicate in _INDEXES:
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} "
                f"ON organizations ({col}) WHERE {predicate}"
            )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for name, _col, _predicate in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
