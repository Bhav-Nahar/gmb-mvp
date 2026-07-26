"""add organizations.auto_reply_mode (template | ai)

Lets an org run the existing auto-reply automation off the LLM instead of its
reply templates. Defaults to 'template' so behaviour is unchanged on upgrade.

Revision ID: ar_2026_ai_mode
Revises: lpseo_2026_l4
Create Date: 2026-07-26

"""
from alembic import op
import sqlalchemy as sa

revision = "ar_2026_ai_mode"
down_revision = "lpseo_2026_l4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "organizations",
        sa.Column("auto_reply_mode", sa.String(), nullable=False, server_default="template"),
    )


def downgrade():
    op.drop_column("organizations", "auto_reply_mode")
