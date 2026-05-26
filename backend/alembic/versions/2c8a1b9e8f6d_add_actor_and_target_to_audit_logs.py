"""add_actor_and_target_to_audit_logs

Revision ID: 2c8a1b9e8f6d
Revises: dabb5ab65d4a
Create Date: 2026-05-25 23:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2c8a1b9e8f6d'
down_revision = 'dabb5ab65d4a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add actor_user_id and target_user_id to audit_logs table
    op.add_column('audit_logs', sa.Column('actor_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True))
    op.add_column('audit_logs', sa.Column('target_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True))


def downgrade() -> None:
    # Remove actor_user_id and target_user_id from audit_logs table
    op.drop_column('audit_logs', 'target_user_id')
    op.drop_column('audit_logs', 'actor_user_id')
