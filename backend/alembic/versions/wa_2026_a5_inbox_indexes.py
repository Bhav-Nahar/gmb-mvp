"""Drop two redundant indexes on whatsapp_messages

Both were habit, not need, and every index is paid for on each inbound webhook
write — the one path on this table that must stay fast, because a slow webhook
is a webhook Meta retries.

  * ix_whatsapp_messages_organization_id — the composite
    (organization_id, phone, created_at) already leads on organization_id, so
    Postgres uses it for org-only lookups.
  * ix_whatsapp_messages_phone — nothing queries a phone without its
    organization. Cross-tenant lookup by number is not a feature; it is a
    tenancy leak.

The UNIQUE index on wamid stays: it is the webhook dedupe, not an optimisation.

Revision ID: wa_2026_a5
Revises: wa_2026_a4
"""
from alembic import op

revision = "wa_2026_a5"
down_revision = "wa_2026_a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_whatsapp_messages_organization_id", table_name="whatsapp_messages")
    op.drop_index("ix_whatsapp_messages_phone", table_name="whatsapp_messages")


def downgrade() -> None:
    op.create_index("ix_whatsapp_messages_organization_id", "whatsapp_messages",
                    ["organization_id"])
    op.create_index("ix_whatsapp_messages_phone", "whatsapp_messages", ["phone"])
