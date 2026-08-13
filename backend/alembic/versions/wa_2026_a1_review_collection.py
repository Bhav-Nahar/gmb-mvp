"""WhatsApp review collection: per-org WABA, review requests, suppressions

Additive only. Creates three new tables and touches nothing that exists, so
`downgrade()` removes the feature completely with no trace on existing data.

Revision ID: wa_2026_a1
Revises: ops_2026_c1
"""
from alembic import op
import sqlalchemy as sa


revision = "wa_2026_a1"
down_revision = "ops_2026_c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("waba_id", sa.String(), nullable=True),
        sa.Column("phone_number_id", sa.String(), nullable=True),
        sa.Column("display_phone_number", sa.String(), nullable=True),
        sa.Column("verified_name", sa.String(), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("status_detail", sa.Text(), nullable=True),
        sa.Column("quality_rating", sa.String(), nullable=True),
        sa.Column("messaging_tier", sa.String(), nullable=True),
        sa.Column("daily_send_limit", sa.Integer(), nullable=True),
        sa.Column("template_name", sa.String(), nullable=True),
        sa.Column("template_status", sa.String(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_whatsapp_accounts_org"),
    )
    op.create_index("ix_whatsapp_accounts_organization_id", "whatsapp_accounts", ["organization_id"])
    op.create_index("ix_whatsapp_accounts_waba_id", "whatsapp_accounts", ["waba_id"])
    # The webhook's routing lookup, on every inbound event.
    op.create_index("ix_whatsapp_accounts_phone_number_id", "whatsapp_accounts", ["phone_number_id"])
    op.create_index("ix_whatsapp_accounts_status", "whatsapp_accounts", ["status"])

    op.create_table(
        "review_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("location_id", sa.Integer(), nullable=False),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("customer_name", sa.String(), nullable=True),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="queued", nullable=False),
        sa.Column("wamid", sa.String(), nullable=True),
        sa.Column("source", sa.String(), server_default="manual", nullable=False),
        sa.Column("batch_id", sa.String(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_review_requests_token"),
    )
    op.create_index("ix_review_requests_organization_id", "review_requests", ["organization_id"])
    op.create_index("ix_review_requests_location_id", "review_requests", ["location_id"])
    op.create_index("ix_review_requests_phone", "review_requests", ["phone"])
    op.create_index("ix_review_requests_token", "review_requests", ["token"])
    op.create_index("ix_review_requests_status", "review_requests", ["status"])
    # Delivery-status webhooks carry only the wamid; this is the join back.
    op.create_index("ix_review_requests_wamid", "review_requests", ["wamid"])
    op.create_index("ix_review_requests_batch_id", "review_requests", ["batch_id"])
    # Frequency cap: "have we messaged this number recently?"
    op.create_index("ix_review_requests_org_phone_created", "review_requests",
                    ["organization_id", "phone", "created_at"])
    op.create_index("ix_review_requests_location_created", "review_requests",
                    ["location_id", "created_at"])

    op.create_table(
        "review_suppressions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), server_default="manual", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "phone", name="uq_review_suppressions_org_phone"),
    )
    op.create_index("ix_review_suppressions_organization_id", "review_suppressions", ["organization_id"])
    op.create_index("ix_review_suppressions_phone", "review_suppressions", ["phone"])


def downgrade() -> None:
    op.drop_table("review_suppressions")
    op.drop_table("review_requests")
    op.drop_table("whatsapp_accounts")
