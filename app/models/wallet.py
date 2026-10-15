from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TransactionResource(str, Enum):
    TEST_STARS = "TEST_STARS"
    SPINS = "SPINS"


class TransactionReason(str, Enum):
    WELCOME_SPIN = "WELCOME_SPIN"
    PURCHASE = "PURCHASE"
    ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT"
    SPIN = "SPIN"


class UserWallet(Base):
    __tablename__ = "user_wallets"
    __table_args__ = (UniqueConstraint("user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    test_stars_balance: Mapped[int] = mapped_column(Integer, default=0)
    spins_balance: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="wallet")
    transactions: Mapped[list["WalletTransaction"]] = relationship(back_populates="wallet", cascade="all, delete-orphan")


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("user_wallets.id", ondelete="CASCADE"), index=True)
    resource: Mapped[TransactionResource] = mapped_column(Enum("TEST_STARS", "SPINS", name="transactionresource"))
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[TransactionReason] = mapped_column(Enum("WELCOME_SPIN", "PURCHASE", "ADMIN_ADJUSTMENT", "SPIN", name="transactionreason"))
    performed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    wallet: Mapped["UserWallet"] = relationship(back_populates="transactions")
