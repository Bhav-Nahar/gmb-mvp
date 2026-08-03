"""Agency white-label branding on organizations.

Four columns, no new table: an org is either an agency (is_agency, flipped by a
super-admin) or it isn't. When it is, its own logo/website/colour replace Pinzo's
on exported reports. NULL brand fields = fall back to Pinzo, so an agency that
enables the flag but uploads nothing still gets a working export.

Revision ID: wl_2026_b1
Revises: pc_2026_a1
"""
import sqlalchemy as sa
from alembic import op

revision = "wl_2026_b1"
down_revision = "pc_2026_a1"
branch_labels = None
depends_on = None

COLUMNS = [
    sa.Column("is_agency", sa.Boolean(), nullable=False,
              server_default=sa.text("false")),
    sa.Column("brand_name", sa.String(), nullable=True),
    sa.Column("brand_logo_url", sa.String(), nullable=True),
    sa.Column("brand_website_url", sa.String(), nullable=True),
]


def upgrade() -> None:
    for col in COLUMNS:
        op.add_column("organizations", col)


def downgrade() -> None:
    for col in reversed(COLUMNS):
        op.drop_column("organizations", col.name)
