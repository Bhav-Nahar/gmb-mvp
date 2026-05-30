"""merge multiple heads

Revision ID: 3c9354df6c8b
Revises: 23cb437ced7d, 3d9b2c8e9f7a
Create Date: 2026-05-29 22:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3c9354df6c8b'
down_revision = ('23cb437ced7d', '3d9b2c8e9f7a')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
