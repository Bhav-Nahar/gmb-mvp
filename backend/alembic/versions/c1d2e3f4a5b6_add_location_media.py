"""add_location_media

Revision ID: c1d2e3f4a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-06-13

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


location_media_status = sa.Enum(
    'Pending', 'Publishing', 'Published', 'Failed', 'Rejected',
    name='locationmediastatus',
)


def upgrade() -> None:
    op.create_table(
        'location_media',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('source_media_id', sa.Integer(), nullable=True),
        sa.Column('gbp_category', sa.String(), nullable=False, server_default='ADDITIONAL'),
        sa.Column('gbp_resource_name', sa.String(), nullable=True),
        sa.Column('media_key', sa.String(), nullable=True),
        sa.Column('source_url', sa.String(), nullable=False),
        sa.Column('view_count', sa.Integer(), nullable=True),
        sa.Column('publish_status', location_media_status, nullable=False, server_default='Pending'),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('google_error_code', sa.String(), nullable=True),
        sa.Column('publish_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_media_id'], ['post_media.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('location_media', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_location_media_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_location_media_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_location_media_location_id'), ['location_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_location_media_publish_status'), ['publish_status'], unique=False)
        batch_op.create_index('idx_location_media_location_status', ['location_id', 'publish_status'], unique=False)
        batch_op.create_index('idx_location_media_org_created', ['organization_id', 'created_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('location_media', schema=None) as batch_op:
        batch_op.drop_index('idx_location_media_org_created')
        batch_op.drop_index('idx_location_media_location_status')
        batch_op.drop_index(batch_op.f('ix_location_media_publish_status'))
        batch_op.drop_index(batch_op.f('ix_location_media_location_id'))
        batch_op.drop_index(batch_op.f('ix_location_media_organization_id'))
        batch_op.drop_index(batch_op.f('ix_location_media_id'))

    op.drop_table('location_media')
    location_media_status.drop(op.get_bind(), checkfirst=True)
