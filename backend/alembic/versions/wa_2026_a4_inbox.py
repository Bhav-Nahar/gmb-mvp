"""WhatsApp inbox: store inbound and outbound messages

One new table. Nothing is backfilled: review requests stay in `review_requests`
and the inbox merges the two on read, so there is no data migration to get wrong.
Customer replies received before this ran were never stored and are gone —
Meta does not let us fetch history.

Revision ID: wa_2026_a4
Revises: wa_2026_a3
"""
import sqlalchemy as sa
from alembic import op

revision = "wa_2026_a4"
down_revision = "wa_2026_a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("message_type", sa.String(), nullable=False, server_default="text"),
        sa.Column("wamid", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="sent"),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("sent_by_user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_whatsapp_messages_organization_id", "whatsapp_messages",
                    ["organization_id"])
    op.create_index("ix_whatsapp_messages_phone", "whatsapp_messages", ["phone"])
    # Unique, not just indexed: this is the dedupe for Meta's webhook retries.
    op.create_index("ix_whatsapp_messages_wamid", "whatsapp_messages", ["wamid"], unique=True)
    op.create_index("ix_wa_messages_org_phone_created", "whatsapp_messages",
                    ["organization_id", "phone", "created_at"])
    op.create_index("ix_wa_messages_org_direction_created", "whatsapp_messages",
                    ["organization_id", "direction", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_wa_messages_org_direction_created", table_name="whatsapp_messages")
    op.drop_index("ix_wa_messages_org_phone_created", table_name="whatsapp_messages")
    op.drop_index("ix_whatsapp_messages_wamid", table_name="whatsapp_messages")
    op.drop_index("ix_whatsapp_messages_phone", table_name="whatsapp_messages")
    op.drop_index("ix_whatsapp_messages_organization_id", table_name="whatsapp_messages")
    op.drop_table("whatsapp_messages")
