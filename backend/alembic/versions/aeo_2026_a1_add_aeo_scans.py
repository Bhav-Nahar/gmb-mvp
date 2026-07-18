"""add aeo_scans table

Revision ID: aeo_2026_a1
Revises: usr_phone_2026
Create Date: 2026-07-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "aeo_2026_a1"
down_revision = "usr_phone_2026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "aeo_scans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", sa.Integer(),
                  sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="Pending"),
        sa.Column("ai_visibility_score", sa.Integer(), nullable=True),
        sa.Column("score_delta", sa.Integer(), nullable=True),
        sa.Column("queries_tracked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_aeo_scans_organization_id", "aeo_scans", ["organization_id"])
    op.create_index("ix_aeo_scans_location_id", "aeo_scans", ["location_id"])
    op.create_index("idx_aeo_scans_location_created", "aeo_scans", ["location_id", "created_at"])


def downgrade():
    op.drop_index("idx_aeo_scans_location_created", table_name="aeo_scans")
    op.drop_index("ix_aeo_scans_location_id", table_name="aeo_scans")
    op.drop_index("ix_aeo_scans_organization_id", table_name="aeo_scans")
    op.drop_table("aeo_scans")
