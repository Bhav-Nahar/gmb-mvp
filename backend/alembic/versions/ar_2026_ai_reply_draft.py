"""add reviews.ai_reply_draft

Holds a generated-and-validated AI reply whose Google POST failed, so the retry
reuses it instead of spending another AI credit on a second generation.

Revision ID: ar_2026_ai_draft
Revises: ar_2026_ai_mode
Create Date: 2026-07-27

"""
from alembic import op
import sqlalchemy as sa

revision = "ar_2026_ai_draft"
down_revision = "ar_2026_ai_mode"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reviews", sa.Column("ai_reply_draft", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("reviews", "ai_reply_draft")
