"""fix_invite_index_pending_and_in_progress

Revision ID: a1b2c3d4e5f6
Revises: f7b2c1d9e8a3
Create Date: 2026-05-26 23:24:00.000000

The previous index (uq_active_invite_email_org) only covered status = 'pending'.
The service layer, however, treats both 'pending' and 'in_progress' as active
states and blocks new invites for either.  The DB constraint did not match that
logic, so a race-condition could produce two active invites for the same email
in an org.  This migration replaces the old index with one whose predicate covers
both statuses, closing the gap.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f7b2c1d9e8a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old partial index (only guarded 'pending')
    op.drop_index('uq_active_invite_email_org', table_name='invites')

    # Recreate it covering both active states
    op.create_index(
        'uq_active_invite_email_org',
        'invites',
        ['email', 'organization_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'in_progress')")
    )


def downgrade() -> None:
    # Restore the old narrower index
    op.drop_index('uq_active_invite_email_org', table_name='invites')

    op.create_index(
        'uq_active_invite_email_org',
        'invites',
        ['email', 'organization_id'],
        unique=True,
        postgresql_where=sa.text("status = 'pending'")
    )
