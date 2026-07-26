"""add lpseo_leads table (public Local-SEO landing-page enquiries)

Until now the audit form only emailed the super-admins, so any Resend failure lost
the lead silently while the visitor saw a success screen. Persist it first, email
second.

Revision ID: lpseo_2026_l2
Revises: cost_2026_sent_att
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa


revision = "lpseo_2026_l2"
down_revision = "cost_2026_sent_att"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "lpseo_leads",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("clinic", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("website", sa.String(), nullable=True),
        sa.Column("locations", sa.String(), nullable=True),
        sa.Column("goal", sa.String(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("page", sa.String(), nullable=True),
        sa.Column("utm_source", sa.String(), nullable=True),
        sa.Column("utm_medium", sa.String(), nullable=True),
        sa.Column("utm_campaign", sa.String(), nullable=True),
        sa.Column("gclid", sa.String(), nullable=True),
        sa.Column("landing_page", sa.String(), nullable=True),
        sa.Column("emailed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lpseo_leads_page", "lpseo_leads", ["page"])
    op.create_index("ix_lpseo_leads_created_at", "lpseo_leads", ["created_at"])


def downgrade():
    op.drop_index("ix_lpseo_leads_created_at", table_name="lpseo_leads")
    op.drop_index("ix_lpseo_leads_page", table_name="lpseo_leads")
    op.drop_table("lpseo_leads")
