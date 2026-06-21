"""add_local_rank_scans

Revision ID: e5a8b3c1d2f4
Revises: d4f7a1c2e9b3
Create Date: 2026-06-20 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e5a8b3c1d2f4'
down_revision = 'd4f7a1c2e9b3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('local_rank_scans',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.Column('location_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('keyword', sa.String(), nullable=False),
    sa.Column('grid_size', sa.Integer(), nullable=False),
    sa.Column('radius_miles', sa.Float(), nullable=False),
    sa.Column('status', sa.String(), server_default='Pending', nullable=False),
    sa.Column('avg_rank', sa.Float(), nullable=True),
    sa.Column('solv', sa.Float(), nullable=True),
    sa.Column('found_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('total_cells', sa.Integer(), server_default='0', nullable=False),
    sa.Column('cells', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('credits_charged', sa.Integer(), server_default='0', nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('local_rank_scans', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_local_rank_scans_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_local_rank_scans_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_local_rank_scans_location_id'), ['location_id'], unique=False)
        batch_op.create_index('idx_local_rank_scans_location_created', ['location_id', 'created_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('local_rank_scans', schema=None) as batch_op:
        batch_op.drop_index('idx_local_rank_scans_location_created')
        batch_op.drop_index(batch_op.f('ix_local_rank_scans_location_id'))
        batch_op.drop_index(batch_op.f('ix_local_rank_scans_organization_id'))
        batch_op.drop_index(batch_op.f('ix_local_rank_scans_id'))

    op.drop_table('local_rank_scans')
