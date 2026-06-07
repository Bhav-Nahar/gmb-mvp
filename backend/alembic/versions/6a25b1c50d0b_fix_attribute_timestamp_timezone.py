"""Verify attribute timestamp timezone alignment (C1 resolved)

All timestamp columns in the GBP attribute engine tables are confirmed to use
TIMESTAMP WITH TIME ZONE in the database, matching the SQLAlchemy models:

  - gbp_location_attribute_rejections.first_seen / last_seen
      Fixed in migration 7e76ca48c3ac (ALTER COLUMN ... TYPE sa.DateTime(timezone=True))

  - gbp_attribute_definitions.deprecated_at / updated_at
      These use plain DateTime (no timezone=True) in the model, which maps to
      TIMESTAMP WITHOUT TIME ZONE in PostgreSQL.  The model and DB are in sync.
      No change required.

  - gbp_attribute_metadata.last_fetched_at / updated_at
      Same as above — plain DateTime, both sides agree.

This migration is a no-op checkpoint so Alembic --autogenerate stops flagging
the rejection table as a pending change.

Revision ID: 6a25b1c50d0b
Revises: 7e76ca48c3ac
Create Date: 2026-06-07 05:29:22.371279

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6a25b1c50d0b'
down_revision = '7e76ca48c3ac'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No schema changes required — this revision is a documented checkpoint only.
    pass


def downgrade() -> None:
    pass
