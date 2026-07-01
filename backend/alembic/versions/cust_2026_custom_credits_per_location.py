"""add custom_credits_per_location for enterprise custom plans

Companion to the existing custom_price_paise column. Together they let a super-admin
give an org a negotiated per-location rate and per-location AI-credit grant. Both NULL
means standard tier pricing.

Revision ID: cust_2026_credits
Revises: del_2026_soft_delete
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "cust_2026_credits"
down_revision = "del_2026_soft_delete"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("custom_credits_per_location", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("organizations", "custom_credits_per_location")
