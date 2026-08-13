"""WhatsApp account lifecycle: recovery, webhook proof, test send, spend ceiling

Additive columns plus one unique constraint. The constraint is the only part
that can fail on existing data — two organizations sharing a phone_number_id —
which is exactly the state it exists to prevent, so it is better found here than
by a tenant receiving another tenant's opt-outs.

Revision ID: wa_2026_a3
Revises: wa_2026_a2
"""
import sqlalchemy as sa
from alembic import op

revision = "wa_2026_a3"
down_revision = "wa_2026_a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("whatsapp_accounts", sa.Column("registration_pin", sa.Text(), nullable=True))
    op.add_column("whatsapp_accounts", sa.Column(
        "app_subscribed", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("whatsapp_accounts", sa.Column(
        "verified_send_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("whatsapp_accounts", sa.Column(
        "monthly_message_limit", sa.Integer(), nullable=True))

    # Accounts connected before this migration have already been sending, so
    # they have proven both facts in production. Backfilling them keeps an
    # existing tenant from being locked out by a new gate they already passed.
    op.execute("""
        UPDATE whatsapp_accounts SET app_subscribed = true, verified_send_at = now()
        WHERE status = 'ready'
    """)

    # NULL phone_number_id stays repeatable (Postgres allows multiple NULLs in a
    # unique index), so half-finished connections are unaffected.
    op.create_unique_constraint(
        "uq_whatsapp_accounts_phone_number_id", "whatsapp_accounts", ["phone_number_id"])


def downgrade() -> None:
    op.drop_constraint("uq_whatsapp_accounts_phone_number_id", "whatsapp_accounts",
                       type_="unique")
    op.drop_column("whatsapp_accounts", "monthly_message_limit")
    op.drop_column("whatsapp_accounts", "verified_send_at")
    op.drop_column("whatsapp_accounts", "app_subscribed")
    op.drop_column("whatsapp_accounts", "registration_pin")
