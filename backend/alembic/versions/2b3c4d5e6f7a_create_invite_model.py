"""create_invite_model

Revision ID: 2b3c4d5e6f7a
Revises: 1a2b3c4d5e6f
Create Date: 2026-05-20 21:13:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2b3c4d5e6f7a'
down_revision = '1a2b3c4d5e6f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create invites table
    op.create_table(
        'invites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(), server_default='Staff', nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('invited_by_user_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_invites_id'), 'invites', ['id'], unique=False)
    op.create_index(op.f('ix_invites_email'), 'invites', ['email'], unique=False)
    op.create_index(op.f('ix_invites_token'), 'invites', ['token'], unique=True)
    
    # Create partial unique index to prevent duplicate active (pending) invites
    op.create_index(
        'uq_active_invite_email_org',
        'invites',
        ['email', 'organization_id'],
        unique=True,
        postgresql_where=sa.text("status = 'pending'")
    )


def downgrade() -> None:
    op.drop_index('uq_active_invite_email_org', table_name='invites')
    op.drop_index(op.f('ix_invites_token'), table_name='invites')
    op.drop_index(op.f('ix_invites_email'), table_name='invites')
    op.drop_index(op.f('ix_invites_id'), table_name='invites')
    op.drop_table('invites')
