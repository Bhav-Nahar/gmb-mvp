"""holidays table

Revision ID: hol_2026_d1e6
Revises: ms_push_c9d5
Create Date: 2026-06-26

"""
from alembic import op
import sqlalchemy as sa


revision = 'hol_2026_d1e6'
down_revision = 'ms_push_c9d5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'holidays',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('category', sa.String(), server_default='festival', nullable=False),
        sa.Column('region', sa.String(), nullable=True),
        sa.Column('country', sa.String(), server_default='IN', nullable=False),
        sa.Column('source', sa.String(), server_default='library', nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('date', 'name', 'region', name='uq_holiday_date_name_region'),
    )
    with op.batch_alter_table('holidays', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_holidays_date'), ['date'])
        batch_op.create_index('idx_holidays_date_range', ['date'])


def downgrade() -> None:
    with op.batch_alter_table('holidays', schema=None) as batch_op:
        batch_op.drop_index('idx_holidays_date_range')
        batch_op.drop_index(batch_op.f('ix_holidays_date'))
    op.drop_table('holidays')
