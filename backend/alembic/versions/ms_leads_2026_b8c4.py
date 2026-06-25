"""microsite leads table + location.lead_email

Revision ID: ms_leads_b8c4
Revises: ms_global_slug_a7f3
Create Date: 2026-06-25

"""
from alembic import op
import sqlalchemy as sa


revision = 'ms_leads_b8c4'
down_revision = 'ms_global_slug_a7f3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'leads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='new'),
        sa.Column('source', sa.String(), nullable=False, server_default='microsite'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_leads_organization_id'), ['organization_id'])
        batch_op.create_index(batch_op.f('ix_leads_location_id'), ['location_id'])

    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lead_email', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.drop_column('lead_email')
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_leads_location_id'))
        batch_op.drop_index(batch_op.f('ix_leads_organization_id'))
    op.drop_table('leads')
