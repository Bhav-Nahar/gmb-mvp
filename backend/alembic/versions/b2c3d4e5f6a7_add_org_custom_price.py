"""add custom_price_paise to organizations

Recreated: the original migration file was lost (only a stale .pyc remained), but
the revision was already applied to the database and is the current alembic head.
This restores the source so alembic can locate the revision again. Adds a nullable
per-organization custom price override (paise); null means use standard pricing.

Revision ID: b2c3d4e5f6a7
Revises: b8d4f1a2c3e5
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "b8d4f1a2c3e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("custom_price_paise", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "custom_price_paise")
