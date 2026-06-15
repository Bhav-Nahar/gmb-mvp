"""add_posts_target_locations_and_schedule_index

Revision ID: ed05ec24150a
Revises: f4a5b6c7d8e9
Create Date: 2026-06-14 18:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'ed05ec24150a'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('posts', sa.Column('target_location_ids', sa.JSON(), nullable=True))
    op.create_index(
        'idx_posts_scheduled_publish',
        'posts',
        ['scheduled_at'],
        postgresql_where=sa.text("status = 'Scheduled'")
    )

def downgrade():
    op.drop_index('idx_posts_scheduled_publish', table_name='posts', postgresql_where=sa.text("status = 'Scheduled'"))
    op.drop_column('posts', 'target_location_ids')
