"""normalize_legacy_staff_role

Revision ID: f7b2c1d9e8a3
Revises: e2f3g4h5i6j7
Create Date: 2026-05-24 21:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f7b2c1d9e8a3"
down_revision = "e2f3g4h5i6j7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Audit-safe normalization: legacy Staff roles are mapped to Store Manager.
    op.execute("CREATE TEMP TABLE migrated_staff_users AS SELECT id FROM users WHERE role = 'Staff'")
    op.execute("UPDATE users SET role = 'Store Manager' WHERE role = 'Staff'")

    # Keep Store Manager valid: exactly one assigned location. Otherwise downgrade safely.
    op.execute(
        """
        UPDATE users u
        SET role = 'Viewer',
            viewer_scope = 'organization'
        WHERE u.id IN (SELECT id FROM migrated_staff_users)
          AND u.role = 'Store Manager'
          AND (
                SELECT COUNT(*) FROM user_location_access ula
                WHERE ula.user_id = u.id
              ) <> 1
        """
    )

    # Normalize invite roles for non-accepted invites only.
    op.execute(
        """
        UPDATE invites
        SET role = 'Store Manager'
        WHERE role = 'Staff'
          AND status <> 'accepted'
        """
    )

    op.execute("DROP TABLE migrated_staff_users")


def downgrade() -> None:
    # Revert normalized role labels for records touched by this migration pattern.
    op.execute("UPDATE users SET role = 'Staff' WHERE role = 'Store Manager'")
    op.execute("UPDATE invites SET role = 'Staff' WHERE role = 'Store Manager' AND status <> 'accepted'")

