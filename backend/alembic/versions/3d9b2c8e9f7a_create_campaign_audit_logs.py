"""Create campaign audit logs

Revision ID: 3d9b2c8e9f7a
Revises: 4ba432de4180
Create Date: 2026-05-29 16:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '3d9b2c8e9f7a'
down_revision = '4ba432de4180'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table('campaign_audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.Column('campaign_id', sa.Integer(), nullable=False),
    sa.Column('actor_user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(), nullable=False),
    sa.Column('previous_status', sa.String(), nullable=True),
    sa.Column('new_status', sa.String(), nullable=True),
    sa.Column('log_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('campaign_audit_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_campaign_audit_logs_id'), ['id'], unique=False)

def downgrade() -> None:
    with op.batch_alter_table('campaign_audit_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_campaign_audit_logs_id'))
    op.drop_table('campaign_audit_logs')
