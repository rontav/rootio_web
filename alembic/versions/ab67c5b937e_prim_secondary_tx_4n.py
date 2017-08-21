"""prim_secondary_tx_4n

Revision ID: ab67c5b937e
Revises: 26289f11869b
Create Date: 2017-08-18 22:20:49.611969

"""

# revision identifiers, used by Alembic.
revision = 'ab67c5b937e'
down_revision = '26289f11869b'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('radio_station', sa.Column('primary_transmitter_phone_id', sa.Integer(), nullable=True))
    op.add_column('radio_station', sa.Column('secondary_transmitter_phone_id', sa.Integer(), nullable=True))
    op.drop_column('radio_station', u'cloud_phone_id')
    op.drop_column('radio_station', u'transmitter_phone_id')
    ### end Alembic commands ###


def downgrade():
    ### commands auto generated by Alembic - please adjust! ###
    op.add_column('radio_station', sa.Column(u'transmitter_phone_id', sa.INTEGER(), nullable=True))
    op.add_column('radio_station', sa.Column(u'cloud_phone_id', sa.INTEGER(), nullable=True))
    op.drop_column('radio_station', 'secondary_transmitter_phone_id')
    op.drop_column('radio_station', 'primary_transmitter_phone_id')
    ### end Alembic commands ###
