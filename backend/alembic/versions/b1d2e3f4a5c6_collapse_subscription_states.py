"""collapse subscription states to trial/active/past_due/locked

Remaps the two removed states onto existing fields:
  - trial_pending_activation -> trial   (trial_ends_at stays NULL = not activated)
  - cancelled_active         -> active  (subscription_ends_at already set)
  - grace_period (phantom)   -> past_due

Data-only migration; subscription_status is a free-text String column so there
is no enum/schema change. No down-migration (MVP).

Revision ID: b1d2e3f4a5c6
Revises: 9a8b150e74ac
Create Date: 2026-06-11
"""
from alembic import op

revision = "b1d2e3f4a5c6"
down_revision = "9a8b150e74ac"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "UPDATE organizations SET subscription_status = 'trial' "
        "WHERE subscription_status = 'trial_pending_activation'"
    )
    op.execute(
        "UPDATE organizations SET subscription_status = 'active' "
        "WHERE subscription_status = 'cancelled_active'"
    )
    op.execute(
        "UPDATE organizations SET subscription_status = 'past_due' "
        "WHERE subscription_status = 'grace_period'"
    )


def downgrade():
    # No down-migration: the collapsed states cannot be unambiguously recovered,
    # and this is acceptable for the MVP.
    pass
