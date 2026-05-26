"""add google_account_id to locations

Revision ID: e2f3g4h5i6j7
Revises: 5c94e212b009
Create Date: 2026-05-24 23:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e2f3g4h5i6j7'
down_revision = '5c94e212b009'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('locations', sa.Column('google_account_id', sa.String(), nullable=True))

def downgrade():
    op.drop_column('locations', 'google_account_id')
