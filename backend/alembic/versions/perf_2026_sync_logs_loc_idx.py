"""perf indexes: sync_logs latest-log subquery + org listing

Revision ID: perf_2026_sl_idx
Revises: flags_2026_kv
Create Date: 2026-07-20 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'perf_2026_sl_idx'
down_revision = 'flags_2026_kv'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # latest-log-per-location subquery on GET /locations
    op.create_index(
        'ix_sync_logs_location_id_id',
        'sync_logs',
        ['location_id', 'id'],
    )
    # org sync-log listing (filter org, order by created_at desc)
    op.create_index(
        'ix_sync_logs_org_id_created_at',
        'sync_logs',
        ['organization_id', 'created_at'],
    )
    # NOTE: the publish-scheduler scan is already covered by the partial index
    # idx_posts_scheduled_publish (scheduled_at WHERE status='Scheduled').


def downgrade() -> None:
    op.drop_index('ix_sync_logs_org_id_created_at', table_name='sync_logs')
    op.drop_index('ix_sync_logs_location_id_id', table_name='sync_logs')
