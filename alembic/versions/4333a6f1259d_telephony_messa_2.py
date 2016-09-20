"""telephony_messa_2

Revision ID: 4333a6f1259d
Revises: 423f8bc6e44
Create Date: 2016-08-25 14:59:06.131010

"""

# revision identifiers, used by Alembic.
revision = '4333a6f1259d'
down_revision = '423f8bc6e44'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column(u'telephony_call', sa.Column('station_id', sa.Integer(), nullable=True))
    op.add_column(u'telephony_message', sa.Column('station_id', sa.Integer(), nullable=True))
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.drop_column(u'telephony_message', 'station_id')
    op.drop_column(u'telephony_call', 'station_id')
    ### end Alembic commands ###
