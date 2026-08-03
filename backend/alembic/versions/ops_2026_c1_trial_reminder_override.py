"""Trial-ending reminder stamp + super-admin trial-abuse override.

trial_reminder_sent_at is the idempotency key for the hourly "your trial ends
tomorrow" sweep (nobody was warning phone-trial customers at all, and they have no
Razorpay mandate to send a pre-debit notice for them).

allow_extra_trial lets a super-admin forgive the one-trial-per-identity guard for a
customer who signed up on the wrong Google account, instead of hand-editing the DB.

Revision ID: ops_2026_c1
"""
import sqlalchemy as sa
from alembic import op

revision = "ops_2026_c1"
down_revision = "cust_2026_tier_prices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("trial_reminder_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("organizations", sa.Column("allow_extra_trial", sa.Boolean(), nullable=False,
                                             server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("organizations", "allow_extra_trial")
    op.drop_column("organizations", "trial_reminder_sent_at")
