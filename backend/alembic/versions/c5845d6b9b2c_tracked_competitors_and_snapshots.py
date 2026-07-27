"""tracked competitors and snapshots

Revision ID: c5845d6b9b2c
Revises: ar_2026_ai_draft
Create Date: 2026-07-27 18:56:43.351080

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5845d6b9b2c'
down_revision = 'ar_2026_ai_draft'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('tracked_competitors',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.Column('location_id', sa.Integer(), nullable=False),
    sa.Column('place_id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('category', sa.String(), nullable=True),
    sa.Column('address', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('location_id', 'place_id', name='uq_tracked_competitor_location_place')
    )
    with op.batch_alter_table('tracked_competitors', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tracked_competitors_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tracked_competitors_location_id'), ['location_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tracked_competitors_organization_id'), ['organization_id'], unique=False)

    op.create_table('competitor_snapshots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('competitor_id', sa.Integer(), nullable=False),
    sa.Column('scan_id', sa.Integer(), nullable=True),
    sa.Column('rating', sa.Float(), nullable=True),
    sa.Column('review_count', sa.Integer(), nullable=True),
    sa.Column('photo_count', sa.Integer(), nullable=True),
    sa.Column('best_rank', sa.Integer(), nullable=True),
    sa.Column('avg_rank', sa.Float(), nullable=True),
    sa.Column('appearances', sa.Integer(), nullable=True),
    sa.Column('total_cells', sa.Integer(), nullable=True),
    sa.Column('keyword', sa.String(), nullable=True),
    sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['competitor_id'], ['tracked_competitors.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['scan_id'], ['local_rank_scans.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('competitor_snapshots', schema=None) as batch_op:
        batch_op.create_index('ix_competitor_snapshots_comp_captured', ['competitor_id', 'captured_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_competitor_snapshots_competitor_id'), ['competitor_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_competitor_snapshots_id'), ['id'], unique=False)


def downgrade() -> None:
    op.drop_table('competitor_snapshots')
    op.drop_table('tracked_competitors')
