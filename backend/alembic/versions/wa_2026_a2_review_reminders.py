"""Reminder tracking on review requests.

Two columns rather than a reminders table: a reminder is the same ask down the
same link, so it belongs on the row that owns the token. A separate table would
duplicate the phone, the location and the token for no new fact.

Revision ID: wa_2026_a2
Revises: wa_2026_a1
"""
import sqlalchemy as sa
from alembic import op

revision = "wa_2026_a2"
down_revision = "wa_2026_a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("review_requests", sa.Column(
        "reminder_count", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("review_requests", sa.Column(
        "last_reminder_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("review_requests", "last_reminder_at")
    op.drop_column("review_requests", "reminder_count")
