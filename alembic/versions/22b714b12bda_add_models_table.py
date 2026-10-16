"""add_models_table

Revision ID: 22b714b12bda
Revises: 306fe5ab17d0
Create Date: 2026-10-16 23:45:49.126752

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '22b714b12bda'
down_revision: Union[str, None] = '306fe5ab17d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'models',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('owner_user_id', sa.Integer(), nullable=False),
        sa.Column('bot_token', sa.String(length=128), nullable=True),
        sa.Column('theme_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_models_owner_user_id'), 'models', ['owner_user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_models_owner_user_id'), table_name='models')
    op.drop_table('models')
