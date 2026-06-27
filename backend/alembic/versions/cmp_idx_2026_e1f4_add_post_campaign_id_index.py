"""add index on posts.campaign_id

Speeds up the per-campaign Post lookup (app/tasks.py — Post.campaign_id filter),
the one campaign filter that wasn't already covered by an index. PublishJob.campaign_id
is already served by idx_publish_jobs_campaign_status.

Revision ID: cmp_idx_2026_e1f4
Revises: hol_2026_d1e6
Create Date: 2026-06-27
"""
from alembic import op

revision = "cmp_idx_2026_e1f4"
down_revision = "hol_2026_d1e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_posts_campaign_id", "posts", ["campaign_id"])


def downgrade():
    op.drop_index("ix_posts_campaign_id", table_name="posts")
