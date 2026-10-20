"""add_spin_mechanics_epic5

Revision ID: b1c2d3e4f5a6
Revises: 22b714b12bda
Create Date: 2026-10-20 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = '22b714b12bda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    # --- wheels.model_id -------------------------------------------------------
    op.add_column('wheels', sa.Column('model_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_wheels_model_id'), 'wheels', ['model_id'], unique=False)

    # --- wheel_segments: reward fields + nullable content_item_id --------------
    if is_sqlite:
        with op.batch_alter_table('wheel_segments', recreate='always') as batch_op:
            batch_op.alter_column(
                'content_item_id', existing_type=sa.Integer(), existing_nullable=False, nullable=True
            )
            batch_op.add_column(
                sa.Column(
                    'reward_type',
                    sa.Enum('none', 'gems', 'spins', name='rewardtype'),
                    nullable=False,
                    server_default='none',
                )
            )
            batch_op.add_column(
                sa.Column('reward_gems', sa.Integer(), nullable=False, server_default='0')
            )
            batch_op.add_column(
                sa.Column('reward_spins', sa.Integer(), nullable=False, server_default='0')
            )
    else:
        op.alter_column('wheel_segments', 'content_item_id', existing_type=sa.Integer(), nullable=True)
        op.add_column(
            'wheel_segments',
            sa.Column(
                'reward_type',
                sa.Enum('none', 'gems', 'spins', name='rewardtype'),
                nullable=False,
                server_default='none',
            ),
        )
        op.add_column('wheel_segments', sa.Column('reward_gems', sa.Integer(), nullable=False, server_default='0'))
        op.add_column('wheel_segments', sa.Column('reward_spins', sa.Integer(), nullable=False, server_default='0'))

    # --- content_items: model_id + rarity -------------------------------------
    op.add_column('content_items', sa.Column('model_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_content_items_model_id'), 'content_items', ['model_id'], unique=False)
    op.add_column(
        'content_items',
        sa.Column(
            'rarity',
            sa.Enum('rare', 'legendary', 'mythic', 'eternal', name='rarity'),
            nullable=False,
            server_default='rare',
        ),
    )

    # --- users: last_daily_wheel_spin_at --------------------------------------
    op.add_column(
        'users', sa.Column('last_daily_wheel_spin_at', sa.DateTime(timezone=True), nullable=True)
    )

    # --- models: media spin prices + rarity weights ---------------------------
    op.add_column('models', sa.Column('media_spin_price_gems', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('models', sa.Column('media_spin_price_stars', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('models', sa.Column('rarity_weights_json', sa.Text(), nullable=True))

    # --- spins: new columns + spin_type enum extension ------------------------
    if is_sqlite:
        with op.batch_alter_table('spins', recreate='always') as batch_op:
            batch_op.alter_column(
                'content_item_id', existing_type=sa.Integer(), existing_nullable=False, nullable=True
            )
            batch_op.add_column(sa.Column('model_id', sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column('cost_gems', sa.Integer(), nullable=False, server_default='0'))
            batch_op.add_column(sa.Column('cost_stars', sa.Integer(), nullable=False, server_default='0'))
            batch_op.add_column(sa.Column('reward_gems', sa.Integer(), nullable=False, server_default='0'))
            batch_op.add_column(sa.Column('reward_spins', sa.Integer(), nullable=False, server_default='0'))
            batch_op.add_column(sa.Column('is_duplicate', sa.Boolean(), nullable=False, server_default=sa.false()))
            batch_op.alter_column(
                'spin_type',
                existing_type=sa.Enum('welcome', 'standard', name='spintype'),
                type_=sa.Enum('welcome', 'standard', 'bonus', 'media', name='spintype'),
                existing_nullable=False,
            )
    else:
        op.execute("ALTER TYPE spintype ADD VALUE IF NOT EXISTS 'bonus'")
        op.execute("ALTER TYPE spintype ADD VALUE IF NOT EXISTS 'media'")
        op.execute("ALTER TYPE transactionreason ADD VALUE IF NOT EXISTS 'DAILY_FREE_SPIN'")
        op.execute("ALTER TYPE transactionreason ADD VALUE IF NOT EXISTS 'MEDIA_SPIN_PURCHASE'")
        op.alter_column('spins', 'content_item_id', existing_type=sa.Integer(), nullable=True)
        op.add_column('spins', sa.Column('model_id', sa.Integer(), nullable=True))
        op.add_column('spins', sa.Column('cost_gems', sa.Integer(), nullable=False, server_default='0'))
        op.add_column('spins', sa.Column('cost_stars', sa.Integer(), nullable=False, server_default='0'))
        op.add_column('spins', sa.Column('reward_gems', sa.Integer(), nullable=False, server_default='0'))
        op.add_column('spins', sa.Column('reward_spins', sa.Integer(), nullable=False, server_default='0'))
        op.add_column('spins', sa.Column('is_duplicate', sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_index(op.f('ix_spins_model_id'), 'spins', ['model_id'], unique=False)

    # --- spin_results table ----------------------------------------------------
    op.create_table(
        'spin_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('spin_id', sa.Integer(), nullable=False),
        sa.Column('content_item_id', sa.Integer(), nullable=True),
        sa.Column('reward_gems', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reward_spins', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_duplicate', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('rarity', sa.Enum('rare', 'legendary', 'mythic', 'eternal', name='rarity'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['content_item_id'], ['content_items.id']),
        sa.ForeignKeyConstraint(['spin_id'], ['spins.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('spin_id'),
    )
    op.create_index(op.f('ix_spin_results_spin_id'), 'spin_results', ['spin_id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    op.drop_index(op.f('ix_spin_results_spin_id'), table_name='spin_results')
    op.drop_table('spin_results')

    op.drop_index(op.f('ix_spins_model_id'), table_name='spins')
    if is_sqlite:
        with op.batch_alter_table('spins', recreate='always') as batch_op:
            batch_op.drop_column('is_duplicate')
            batch_op.drop_column('reward_spins')
            batch_op.drop_column('reward_gems')
            batch_op.drop_column('cost_stars')
            batch_op.drop_column('cost_gems')
            batch_op.drop_column('model_id')
            batch_op.alter_column(
                'content_item_id', existing_type=sa.Integer(), existing_nullable=True, nullable=False
            )
            batch_op.alter_column(
                'spin_type',
                existing_type=sa.Enum('welcome', 'standard', 'bonus', 'media', name='spintype'),
                type_=sa.Enum('welcome', 'standard', name='spintype'),
                existing_nullable=False,
            )
    else:
        op.drop_column('spins', 'is_duplicate')
        op.drop_column('spins', 'reward_spins')
        op.drop_column('spins', 'reward_gems')
        op.drop_column('spins', 'cost_stars')
        op.drop_column('spins', 'cost_gems')
        op.drop_column('spins', 'model_id')
        op.alter_column('spins', 'content_item_id', existing_type=sa.Integer(), nullable=False)
        op.execute("ALTER TYPE spintype DROP VALUE IF EXISTS 'media'")
        op.execute("ALTER TYPE spintype DROP VALUE IF EXISTS 'bonus'")

    op.drop_column('models', 'rarity_weights_json')
    op.drop_column('models', 'media_spin_price_stars')
    op.drop_column('models', 'media_spin_price_gems')

    op.drop_column('users', 'last_daily_wheel_spin_at')

    op.drop_column('content_items', 'rarity')
    op.drop_index(op.f('ix_content_items_model_id'), table_name='content_items')
    op.drop_column('content_items', 'model_id')

    if is_sqlite:
        with op.batch_alter_table('wheel_segments', recreate='always') as batch_op:
            batch_op.drop_column('reward_spins')
            batch_op.drop_column('reward_gems')
            batch_op.drop_column('reward_type')
            batch_op.alter_column(
                'content_item_id', existing_type=sa.Integer(), existing_nullable=True, nullable=False
            )
    else:
        op.drop_column('wheel_segments', 'reward_spins')
        op.drop_column('wheel_segments', 'reward_gems')
        op.drop_column('wheel_segments', 'reward_type')
        op.alter_column('wheel_segments', 'content_item_id', existing_type=sa.Integer(), nullable=False)

    op.drop_index(op.f('ix_wheels_model_id'), table_name='wheels')
    op.drop_column('wheels', 'model_id')
