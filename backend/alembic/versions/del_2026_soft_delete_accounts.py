"""soft-delete columns for organizations and users

Super-admin account deletion is a soft delete with a recovery window: deleted_at is
stamped, access is cut off immediately, and a daily task hard-purges anything soft-
deleted longer than the grace period (ACCOUNT_PURGE_GRACE_DAYS). Partial indexes keep
the purge sweep off a full table scan.

Revision ID: del_2026_soft_delete
Revises: re_2026_reassign_cooldown
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "del_2026_soft_delete"
down_revision = "re_2026_reassign_cooldown"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_org_deleted_at "
                   "ON organizations (deleted_at) WHERE deleted_at IS NOT NULL")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_deleted_at "
                   "ON users (deleted_at) WHERE deleted_at IS NOT NULL")


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_users_deleted_at")
            op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_org_deleted_at")
    op.drop_column("users", "deleted_at")
    op.drop_column("organizations", "deleted_at")
