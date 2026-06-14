"""add invoice_url to billing_transactions

Revision ID: b7c8d9e0f1a2
Revises: 4a29ca2897dd
Create Date: 2026-06-13

"""
from alembic import op
import sqlalchemy as sa

revision = 'b7c8d9e0f1a2'
down_revision = '4a29ca2897dd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'billing_transactions',
        sa.Column('invoice_url', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('billing_transactions', 'invoice_url')
