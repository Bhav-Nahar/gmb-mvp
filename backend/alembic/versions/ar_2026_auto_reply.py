"""auto-reply from templates: org toggle + review attribution/attempts

Revision ID: ar_2026_auto_reply
Revises: conv_client_2026
Create Date: 2026-06-29

"""
from alembic import op
import sqlalchemy as sa

revision = "ar_2026_auto_reply"
down_revision = "conv_client_2026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "organizations",
        sa.Column("auto_reply_enabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reviews",
        sa.Column("reply_template_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "reviews",
        sa.Column("auto_reply_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_foreign_key(
        "fk_reviews_reply_template_id",
        "reviews",
        "reply_templates",
        ["reply_template_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("fk_reviews_reply_template_id", "reviews", type_="foreignkey")
    op.drop_column("reviews", "auto_reply_attempts")
    op.drop_column("reviews", "reply_template_id")
    op.drop_column("organizations", "auto_reply_enabled_at")
