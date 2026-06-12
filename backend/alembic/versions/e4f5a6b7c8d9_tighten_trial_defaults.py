"""tighten trial defaults: 3 locations, 10 AI credits

Restricts the free trial entitlement granted to NEW organizations by lowering the
column-level defaults that back the trial:
  - organizations.location_quota          5  -> 3
  - organizations.monthly_ai_credits_balance 200 -> 10

Only affects orgs created AFTER this migration. Existing trial orgs keep whatever
they were granted (no clawback mid-trial).

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-12
"""
from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("organizations", "location_quota", server_default="3")
    op.alter_column("organizations", "monthly_ai_credits_balance", server_default="10")


def downgrade():
    op.alter_column("organizations", "location_quota", server_default="5")
    op.alter_column("organizations", "monthly_ai_credits_balance", server_default="200")
