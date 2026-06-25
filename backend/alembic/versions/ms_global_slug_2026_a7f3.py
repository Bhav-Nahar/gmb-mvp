"""microsite single-level slug: location_slug globally unique

Switches the public URL from /{org_slug}/{location_slug} to /{location_slug},
so location_slug must be globally unique instead of unique-per-org.

Revision ID: ms_global_slug_a7f3
Revises: 56311790c76c
Create Date: 2026-06-24

"""
from alembic import op


revision = 'ms_global_slug_a7f3'
down_revision = '56311790c76c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('microsites', schema=None) as batch_op:
        batch_op.drop_constraint('uq_microsite_org_slug', type_='unique')
        batch_op.create_unique_constraint('uq_microsite_location_slug', ['location_slug'])


def downgrade() -> None:
    with op.batch_alter_table('microsites', schema=None) as batch_op:
        batch_op.drop_constraint('uq_microsite_location_slug', type_='unique')
        batch_op.create_unique_constraint('uq_microsite_org_slug', ['org_slug', 'location_slug'])
