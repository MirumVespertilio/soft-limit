from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TransactionResource(PyEnum):
    TEST_STARS = "TEST_STARS"
    SPINS = "SPINS"


class TransactionReason(PyEnum):
    WELCOME_SPIN = "WELCOME_SPIN"
    PURCHASE = "PURCHASE"
    ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT"
    SPIN = "SPIN"


class UserWallet(Base):
    __tablename__ = "user_wallets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    test_stars_balance: Mapped[int] = mapped_column(Integer, default=0)
    spins_balance: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id"),
        CheckConstraint("test_stars_balance >= 0", name="ck_user_wallets_test_stars_non_negative"),
        CheckConstraint("spins_balance >= 0", name="ck_user_wallets_spins_non_negative"),
    )

    user: Mapped["User"] = relationship(back_populates="wallet")
    transactions: Mapped[list["WalletTransaction"]] = relationship(back_populates="wallet", cascade="all, delete-orphan")


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("user_wallets.id", ondelete="CASCADE"), index=True)
    resource: Mapped[TransactionResource] = mapped_column(SAEnum(TransactionResource, values_callable=lambda x: [e.value for e in x]))
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[TransactionReason] = mapped_column(SAEnum(TransactionReason, values_callable=lambda x: [e.value for e in x]))
    performed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    wallet: Mapped["UserWallet"] = relationship(back_populates="transactions")
