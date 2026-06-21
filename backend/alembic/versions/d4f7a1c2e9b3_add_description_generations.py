"""add_description_generations

Revision ID: d4f7a1c2e9b3
Revises: b2c3d4e5f6a7
Create Date: 2026-06-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd4f7a1c2e9b3'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('description_generations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('organization_id', sa.Integer(), nullable=False),
    sa.Column('location_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('generated_text', sa.Text(), nullable=False),
    sa.Column('char_count', sa.Integer(), nullable=False),
    sa.Column('category_mentioned', sa.String(), nullable=True),
    sa.Column('locality_used', sa.String(), nullable=True),
    sa.Column('improvement_notes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('policy_flags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('description_generations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_description_generations_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_description_generations_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_description_generations_location_id'), ['location_id'], unique=False)
        batch_op.create_index('idx_description_generations_location_created', ['location_id', 'created_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('description_generations', schema=None) as batch_op:
        batch_op.drop_index('idx_description_generations_location_created')
        batch_op.drop_index(batch_op.f('ix_description_generations_location_id'))
        batch_op.drop_index(batch_op.f('ix_description_generations_organization_id'))
        batch_op.drop_index(batch_op.f('ix_description_generations_id'))

    op.drop_table('description_generations')
