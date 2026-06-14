"""add partial unique (razorpay_payment_id, transaction_type) to billing_transactions

Makes credit/charge idempotency a DB guarantee instead of relying solely on the
application-level read-then-insert under the org row lock (BE-BILLING-1). The key
is composite so a later `refund_reversal` row can reference the same payment id as
the original charge without colliding. Partial (WHERE razorpay_payment_id IS NOT
NULL) because reconciliation/system rows legitimately have a null payment id.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-14

"""
from alembic import op
import sqlalchemy as sa


revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None

_INDEX_NAME = 'uq_billing_txn_payment_type'


def upgrade() -> None:
    bind = op.get_bind()
    # Postgres-only partial unique index + a Postgres-only dedup. On SQLite (tests)
    # the table is created fresh per run with no duplicates, so skip entirely.
    if bind.dialect.name != 'postgresql':
        return

    # Remove any pre-existing duplicate (payment_id, type) rows that the prior
    # app-level-only guard could have let through, keeping the earliest row.
    op.execute(
        """
        DELETE FROM billing_transactions a
        USING billing_transactions b
        WHERE a.razorpay_payment_id IS NOT NULL
          AND a.razorpay_payment_id = b.razorpay_payment_id
          AND a.transaction_type = b.transaction_type
          AND a.id > b.id
        """
    )
    op.create_index(
        _INDEX_NAME,
        'billing_transactions',
        ['razorpay_payment_id', 'transaction_type'],
        unique=True,
        postgresql_where=sa.text('razorpay_payment_id IS NOT NULL'),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return
    op.drop_index(_INDEX_NAME, table_name='billing_transactions')
