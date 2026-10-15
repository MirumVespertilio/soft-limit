"""add_processing_delivery_status

Revision ID: 657b84928bb6
Revises: ddd1fd305bd7
Create Date: 2026-10-15 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '657b84928bb6'
down_revision: Union[str, None] = 'ddd1fd305bd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("ALTER TYPE deliverystatus ADD VALUE 'processing'")
        with op.batch_alter_table('media_deliveries') as batch_op:
            batch_op.alter_column(
                'status',
                existing_type=sa.Enum('pending', 'sent', 'failed', name='deliverystatus'),
                type_=sa.Enum('pending', 'processing', 'sent', 'failed', name='deliverystatus'),
                existing_nullable=False,
                postgresql_using="status::deliverystatus",
            )
    else:
        with op.batch_alter_table('media_deliveries') as batch_op:
            batch_op.alter_column(
                'status',
                existing_type=sa.Enum('pending', 'sent', 'failed', name='deliverystatus'),
                type_=sa.Enum('pending', 'processing', 'sent', 'failed', name='deliverystatus'),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # PostgreSQL cannot drop one enum value in-place. Convert the column to
        # text, recreate the enum without processing, then cast back. Any rows
        # still PROCESSING are returned to PENDING as part of the downgrade.
        op.execute("UPDATE media_deliveries SET status = 'pending' WHERE status::text = 'processing'")
        op.execute("ALTER TABLE media_deliveries ALTER COLUMN status TYPE VARCHAR(32) USING status::text")
        op.execute("DROP TYPE deliverystatus")
        op.execute("CREATE TYPE deliverystatus AS ENUM ('pending', 'sent', 'failed')")
        op.execute("ALTER TABLE media_deliveries ALTER COLUMN status TYPE deliverystatus USING status::text::deliverystatus")
    else:
        with op.batch_alter_table('media_deliveries') as batch_op:
            batch_op.alter_column(
                'status',
                existing_type=sa.Enum('pending', 'processing', 'sent', 'failed', name='deliverystatus'),
                type_=sa.Enum('pending', 'sent', 'failed', name='deliverystatus'),
                existing_nullable=False,
            )
