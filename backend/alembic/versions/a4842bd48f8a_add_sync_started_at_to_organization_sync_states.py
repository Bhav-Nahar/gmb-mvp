"""add_sync_started_at_to_organization_sync_states

Revision ID: a4842bd48f8a
Revises: e32ab4b13a89
Create Date: 2026-06-05 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a4842bd48f8a'
down_revision = 'e32ab4b13a89'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add sync_started_at column — records when sync_in_progress was last set to True.
    # Nullable because existing rows (created before this migration) have no start time.
    op.add_column(
        'organization_sync_states',
        sa.Column('sync_started_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('organization_sync_states', 'sync_started_at')
