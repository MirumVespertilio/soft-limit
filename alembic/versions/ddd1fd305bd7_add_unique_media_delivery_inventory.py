"""add_unique_media_delivery_inventory

Revision ID: ddd1fd305bd7
Revises: e416ffbe5630
Create Date: 2026-10-15 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ddd1fd305bd7'
down_revision: Union[str, None] = 'e416ffbe5630'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('media_deliveries') as batch_op:
        batch_op.create_unique_constraint('uq_media_deliveries_inventory_id', ['inventory_id'])


def downgrade() -> None:
    with op.batch_alter_table('media_deliveries') as batch_op:
        batch_op.drop_constraint('uq_media_deliveries_inventory_id', type_='unique')
