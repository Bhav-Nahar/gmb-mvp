"""Add additional_categories to locations

Revision ID: d1e2f3a4b5c6
Revises: c055e8206e83
Create Date: 2026-06-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = 'd1e2f3a4b5c6'
down_revision = 'c055e8206e83'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'additional_categories',
            JSONB(),
            server_default='[]',
            nullable=False,
        ))


def downgrade() -> None:
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.drop_column('additional_categories')
