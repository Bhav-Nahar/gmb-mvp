"""add leaderboard cohort columns

Revision ID: a1c9f4e2b7d0
Revises: 9bca78c19bf6
Create Date: 2026-06-22

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1c9f4e2b7d0'
down_revision = '9bca78c19bf6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('leaderboard_snapshots', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cohort', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('cohort_rank', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('cohort_size', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('leaderboard_snapshots', schema=None) as batch_op:
        batch_op.drop_column('cohort_size')
        batch_op.drop_column('cohort_rank')
        batch_op.drop_column('cohort')
