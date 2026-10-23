"""spin_packages_price_stars

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-10-23 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    if is_sqlite:
        with op.batch_alter_table('spin_packages', recreate='always') as batch_op:
            batch_op.add_column(sa.Column('price_stars', sa.Integer(), nullable=False, server_default='0'))
        with op.batch_alter_table('spin_purchases', recreate='always') as batch_op:
            batch_op.add_column(sa.Column('cost_stars', sa.Integer(), nullable=False, server_default='0'))
    else:
        op.add_column('spin_packages', sa.Column('price_stars', sa.Integer(), nullable=False, server_default='0'))
        op.add_column('spin_purchases', sa.Column('cost_stars', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    if is_sqlite:
        with op.batch_alter_table('spin_purchases', recreate='always') as batch_op:
            batch_op.drop_column('cost_stars')
        with op.batch_alter_table('spin_packages', recreate='always') as batch_op:
            batch_op.drop_column('price_stars')
    else:
        op.drop_column('spin_purchases', 'cost_stars')
        op.drop_column('spin_packages', 'price_stars')
