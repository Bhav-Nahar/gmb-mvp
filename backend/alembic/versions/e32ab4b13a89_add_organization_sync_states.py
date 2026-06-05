"""add_organization_sync_states

Revision ID: e32ab4b13a89
Revises: f35c21fa1306
Create Date: 2026-06-05 21:35:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e32ab4b13a89'
down_revision = 'f35c21fa1306'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'organization_sync_states',
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('last_location_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_review_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_insights_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sync_in_progress', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('last_sync_status', sa.String(length=50), nullable=True),
        sa.Column('last_sync_error', sa.Text(), nullable=True)
    )
    
    # Backfill existing organizations with a default sync state row
    op.execute(
        "INSERT INTO organization_sync_states (organization_id, sync_in_progress) "
        "SELECT id, false FROM organizations "
        "ON CONFLICT DO NOTHING"
    )

def downgrade() -> None:
    op.drop_table('organization_sync_states')
