"""org marketing attribution columns

Revision ID: attr_2026_a1f2
Revises: hol_2026_d1e6
Create Date: 2026-06-27

"""
from alembic import op
import sqlalchemy as sa


revision = 'attr_2026_a1f2'
down_revision = 'hol_2026_d1e6'
branch_labels = None
depends_on = None

_COLS = [
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
    'gclid', 'gbraid', 'wbraid', 'fbclid', 'fbp', 'fbc',
    'landing_page', 'referrer',
]


def upgrade() -> None:
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        for c in _COLS:
            batch_op.add_column(sa.Column(c, sa.String(), nullable=True))
        batch_op.add_column(sa.Column('attribution_captured_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('organizations', schema=None) as batch_op:
        batch_op.drop_column('attribution_captured_at')
        for c in reversed(_COLS):
            batch_op.drop_column(c)
