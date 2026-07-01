"""track last location reassignment for the free-swap cooldown

Owners can choose which locations fill their paid slots for free, but not
arbitrarily often — otherwise active locations could be cycled daily to farm
per-location value beyond the paid quota. This column stamps the last reassignment
so the endpoint can enforce a cooldown.

Revision ID: re_2026_reassign_cooldown
Revises: idx_2026_billing_sweeps
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "re_2026_reassign_cooldown"
down_revision = "idx_2026_billing_sweeps"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "organizations",
        sa.Column("last_location_reassign_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("organizations", "last_location_reassign_at")
