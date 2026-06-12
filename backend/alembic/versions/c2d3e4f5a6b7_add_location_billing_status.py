"""add billing_status to locations for per-location quota enforcement

Adds locations.billing_status ('active' | 'pending_payment'). Existing rows are
backfilled to 'active' via the server_default, so every location currently in the
DB is grandfathered and never goes dark. Only newly detected over-quota locations
are inserted as 'pending_payment' by the sync task.

Also adds a composite (organization_id, billing_status) index for the hot
active-count query used during sync enforcement.

Revision ID: c2d3e4f5a6b7
Revises: b1d2e3f4a5c6
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "c2d3e4f5a6b7"
down_revision = "b1d2e3f4a5c6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "locations",
        sa.Column(
            "billing_status",
            sa.String(),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_locations_org_billing_status",
        "locations",
        ["organization_id", "billing_status"],
    )


def downgrade():
    op.drop_index("ix_locations_org_billing_status", table_name="locations")
    op.drop_column("locations", "billing_status")
