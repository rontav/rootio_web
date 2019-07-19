"""Add deleted attr to community content

Revision ID: 1493003084e8
Revises: 283afd3c9a32
Create Date: 2019-06-26 14:55:48.839270

"""

# revision identifiers, used by Alembic.
revision = '1493003084e8'
down_revision = '283afd3c9a32'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('content_communitycontent', sa.Column('deleted', sa.Boolean(), nullable=True))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('content_communitycontent', 'deleted')
    ### end Alembic commands ###
