"""merge heads

Revision ID: head_merge_001
Revises: a1b2c3d4e5f6, 60e1d4af4858
Create Date: 2026-05-26 23:28:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'head_merge_001'
down_revision = ('a1b2c3d4e5f6', '60e1d4af4858')
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
