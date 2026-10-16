"""migrate_currency_to_gems_and_add_gem_packages

Revision ID: 306fe5ab17d0
Revises: 81be1bbbabef
Create Date: 2026-10-16 23:26:59.014612

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '306fe5ab17d0'
down_revision: Union[str, None] = '81be1bbbabef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Создаем новые таблицы
    op.create_table(
        'gem_packages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('gems_amount', sa.Integer(), nullable=False),
        sa.Column('price_stars', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('gems_amount > 0', name='ck_gem_packages_gems_positive'),
        sa.CheckConstraint('price_stars > 0', name='ck_gem_packages_price_positive'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table(
        'gem_purchases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('package_id', sa.Integer(), nullable=True),
        sa.Column('gems_added', sa.Integer(), nullable=False),
        sa.Column('price_stars', sa.Integer(), nullable=False),
        sa.Column('telegram_payment_charge_id', sa.String(length=128), nullable=True),
        sa.Column('idempotency_key', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['package_id'], ['gem_packages.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'idempotency_key')
    )
    op.create_index(op.f('ix_gem_purchases_user_id'), 'gem_purchases', ['user_id'], unique=False)

    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        # Выполняем чисто через пересоздание таблиц для SQLite
        op.execute("""
            CREATE TABLE spin_packages_new (
                id INTEGER PRIMARY KEY,
                name VARCHAR(128) NOT NULL,
                spins_count INTEGER NOT NULL,
                price_gems INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                position INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_spin_packages_spins_positive CHECK (spins_count > 0),
                CONSTRAINT ck_spin_packages_price_non_negative CHECK (price_gems >= 0)
            )
        """)
        op.execute("""
            INSERT INTO spin_packages_new (id, name, spins_count, price_gems, is_active, position, created_at)
            SELECT id, name, spins_count, price_test_stars, is_active, position, created_at FROM spin_packages
        """)
        op.execute("DROP TABLE spin_packages")
        op.execute("ALTER TABLE spin_packages_new RENAME TO spin_packages")

        op.execute("""
            CREATE TABLE spin_purchases_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                package_id INTEGER NOT NULL,
                price_gems INTEGER NOT NULL DEFAULT 0,
                spins_added INTEGER NOT NULL,
                idempotency_key VARCHAR(64) NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(package_id) REFERENCES spin_packages (id),
                FOREIGN KEY(user_id) REFERENCES users (id),
                UNIQUE (user_id, idempotency_key)
            )
        """)
        op.execute("""
            INSERT INTO spin_purchases_new (id, user_id, package_id, price_gems, spins_added, idempotency_key, created_at)
            SELECT id, user_id, package_id, price_test_stars, spins_added, idempotency_key, created_at FROM spin_purchases
        """)
        op.execute("DROP TABLE spin_purchases")
        op.execute("ALTER TABLE spin_purchases_new RENAME TO spin_purchases")
        op.execute("CREATE INDEX ix_spin_purchases_user_id ON spin_purchases (user_id)")

        op.execute("""
            CREATE TABLE user_wallets_new (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE,
                gems_balance INTEGER NOT NULL DEFAULT 0,
                spins_balance INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
                CONSTRAINT ck_user_wallets_gems_non_negative CHECK (gems_balance >= 0),
                CONSTRAINT ck_user_wallets_spins_non_negative CHECK (spins_balance >= 0)
            )
        """)
        op.execute("""
            INSERT INTO user_wallets_new (id, user_id, gems_balance, spins_balance, updated_at)
            SELECT id, user_id, test_stars_balance, spins_balance, updated_at FROM user_wallets
        """)
        op.execute("DROP TABLE user_wallets")
        op.execute("ALTER TABLE user_wallets_new RENAME TO user_wallets")
    else:
        # Для PostgreSQL и других диалектов с поддержкой ALTER TABLE
        op.alter_column('spin_packages', 'price_test_stars', new_column_name='price_gems')
        op.drop_constraint('ck_spin_packages_price_non_negative', 'spin_packages', type_='check')
        op.create_check_constraint('ck_spin_packages_price_non_negative', 'spin_packages', 'price_gems >= 0')

        op.alter_column('spin_purchases', 'price_test_stars', new_column_name='price_gems')

        op.alter_column('user_wallets', 'test_stars_balance', new_column_name='gems_balance')
        op.drop_constraint('ck_user_wallets_test_stars_non_negative', 'user_wallets', type_='check')
        op.create_check_constraint('ck_user_wallets_gems_non_negative', 'user_wallets', 'gems_balance >= 0')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite':
        op.execute("""
            CREATE TABLE user_wallets_old (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE,
                test_stars_balance INTEGER NOT NULL DEFAULT 0,
                spins_balance INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
                CONSTRAINT ck_user_wallets_test_stars_non_negative CHECK (test_stars_balance >= 0),
                CONSTRAINT ck_user_wallets_spins_non_negative CHECK (spins_balance >= 0)
            )
        """)
        op.execute("""
            INSERT INTO user_wallets_old (id, user_id, test_stars_balance, spins_balance, updated_at)
            SELECT id, user_id, gems_balance, spins_balance, updated_at FROM user_wallets
        """)
        op.execute("DROP TABLE user_wallets")
        op.execute("ALTER TABLE user_wallets_old RENAME TO user_wallets")

        op.execute("""
            CREATE TABLE spin_purchases_old (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                package_id INTEGER NOT NULL,
                price_test_stars INTEGER NOT NULL DEFAULT 0,
                spins_added INTEGER NOT NULL,
                idempotency_key VARCHAR(64) NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(package_id) REFERENCES spin_packages (id),
                FOREIGN KEY(user_id) REFERENCES users (id),
                UNIQUE (user_id, idempotency_key)
            )
        """)
        op.execute("""
            INSERT INTO spin_purchases_old (id, user_id, package_id, price_test_stars, spins_added, idempotency_key, created_at)
            SELECT id, user_id, package_id, price_gems, spins_added, idempotency_key, created_at FROM spin_purchases
        """)
        op.execute("DROP TABLE spin_purchases")
        op.execute("ALTER TABLE spin_purchases_old RENAME TO spin_purchases")
        op.execute("CREATE INDEX ix_spin_purchases_user_id ON spin_purchases (user_id)")

        op.execute("""
            CREATE TABLE spin_packages_old (
                id INTEGER PRIMARY KEY,
                name VARCHAR(128) NOT NULL,
                spins_count INTEGER NOT NULL,
                price_test_stars INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                position INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_spin_packages_spins_positive CHECK (spins_count > 0),
                CONSTRAINT ck_spin_packages_price_non_negative CHECK (price_test_stars >= 0)
            )
        """)
        op.execute("""
            INSERT INTO spin_packages_old (id, name, spins_count, price_test_stars, is_active, position, created_at)
            SELECT id, name, spins_count, price_gems, is_active, position, created_at FROM spin_packages
        """)
        op.execute("DROP TABLE spin_packages")
        op.execute("ALTER TABLE spin_packages_old RENAME TO spin_packages")
    else:
        op.alter_column('user_wallets', 'gems_balance', new_column_name='test_stars_balance')
        op.drop_constraint('ck_user_wallets_gems_non_negative', 'user_wallets', type_='check')
        op.create_check_constraint('ck_user_wallets_test_stars_non_negative', 'user_wallets', 'test_stars_balance >= 0')

        op.alter_column('spin_purchases', 'price_gems', new_column_name='price_test_stars')

        op.alter_column('spin_packages', 'price_gems', new_column_name='price_test_stars')
        op.drop_constraint('ck_spin_packages_price_non_negative', 'spin_packages', type_='check')
        op.create_check_constraint('ck_spin_packages_price_non_negative', 'spin_packages', 'price_test_stars >= 0')

    op.drop_index(op.f('ix_gem_purchases_user_id'), table_name='gem_purchases')
    op.drop_table('gem_purchases')
    op.drop_table('gem_packages')
