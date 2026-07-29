"""add locations.auto_reply_enabled (per-location opt-out)

The org toggle stays the master switch; this lets an org keep auto-reply on but
exclude individual locations. Defaults to true so behaviour is unchanged.

Revision ID: ar_2026_per_loc
Revises: d1a2b3c4e5f6
Create Date: 2026-07-28

"""
from alembic import op
import sqlalchemy as sa

revision = "ar_2026_per_loc"
down_revision = "d1a2b3c4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "locations",
        sa.Column("auto_reply_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade():
    op.drop_column("locations", "auto_reply_enabled")
