"""Per-tier enterprise custom pricing.

`custom_price_paise` was a single negotiated per-location rate that applied to
WHICHEVER tier the client checked out with — so an org priced for Basic could take
Pro at the same rate, and could never be upsold. Replaced by a per-tier map:
{"basic": 79900, "pro": 149900}. Tiers absent from the map bill standard pricing.

Backfills the legacy rate against the org's CURRENT tier, which is the deal that was
actually intended. The old column is left in place (unused by pricing) for one release.

Revision ID: cust_2026_tier_prices
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "cust_2026_tier_prices"
down_revision = "wl_2026_b1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "organizations",
        sa.Column("custom_prices", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        """
        UPDATE organizations
           SET custom_prices = jsonb_build_object(COALESCE(plan_tier, 'basic'), custom_price_paise)
        WHERE custom_price_paise IS NOT NULL
        """
    )


def downgrade():
    op.drop_column("organizations", "custom_prices")
