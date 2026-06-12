"""index post_variants.location_id for health score photo count

Revision ID: 7f3a9c1d2e4b
Revises: fc18f1744ac5
Create Date: 2026-06-12 18:10:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '7f3a9c1d2e4b'
down_revision = 'fc18f1744ac5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        op.f('ix_post_variants_location_id'),
        'post_variants',
        ['location_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_post_variants_location_id'), table_name='post_variants')
