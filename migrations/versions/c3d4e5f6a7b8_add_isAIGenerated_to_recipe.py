"""add isAIGenerated to recipe

Revision ID: c3d4e5f6a7b8
Revises: 203807ef88c1
Create Date: 2026-05-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('isAIGenerated', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('recipes', schema=None) as batch_op:
        batch_op.drop_column('isAIGenerated')
