"""add_model_id_to_spin_purchases_epic6

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-10-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    if is_sqlite:
        with op.batch_alter_table('spin_packages', recreate='always') as batch_op:
            batch_op.add_column(sa.Column('model_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_spin_packages_model_id', 'models', ['model_id'], ['id']
            )
            batch_op.create_index(op.f('ix_spin_packages_model_id'), ['model_id'])
        with op.batch_alter_table('spin_purchases', recreate='always') as batch_op:
            batch_op.add_column(sa.Column('model_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_spin_purchases_model_id', 'models', ['model_id'], ['id']
            )
            batch_op.create_index(op.f('ix_spin_purchases_model_id'), ['model_id'])
    else:
        op.add_column('spin_packages', sa.Column('model_id', sa.Integer(), nullable=True))
        op.create_foreign_key(
            'fk_spin_packages_model_id', 'spin_packages', 'models', ['model_id'], ['id']
        )
        op.create_index(op.f('ix_spin_packages_model_id'), 'spin_packages', ['model_id'], unique=False)

        op.add_column('spin_purchases', sa.Column('model_id', sa.Integer(), nullable=True))
        op.create_foreign_key(
            'fk_spin_purchases_model_id', 'spin_purchases', 'models', ['model_id'], ['id']
        )
        op.create_index(op.f('ix_spin_purchases_model_id'), 'spin_purchases', ['model_id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    if is_sqlite:
        with op.batch_alter_table('spin_purchases', recreate='always') as batch_op:
            batch_op.drop_index(op.f('ix_spin_purchases_model_id'))
            batch_op.drop_constraint('fk_spin_purchases_model_id', type_='foreignkey')
            batch_op.drop_column('model_id')
        with op.batch_alter_table('spin_packages', recreate='always') as batch_op:
            batch_op.drop_index(op.f('ix_spin_packages_model_id'))
            batch_op.drop_constraint('fk_spin_packages_model_id', type_='foreignkey')
            batch_op.drop_column('model_id')
    else:
        op.drop_index(op.f('ix_spin_purchases_model_id'), table_name='spin_purchases')
        op.drop_constraint('fk_spin_purchases_model_id', 'spin_purchases', type_='foreignkey')
        op.drop_column('spin_purchases', 'model_id')

        op.drop_index(op.f('ix_spin_packages_model_id'), table_name='spin_packages')
        op.drop_constraint('fk_spin_packages_model_id', 'spin_packages', type_='foreignkey')
        op.drop_column('spin_packages', 'model_id')
