"""Модели кошелька и транзакций.

GEMS — единственная внутренняя игровая валюта.
Telegram Stars — внешняя валюта Telegram, за которую покупаются GEMS.
spins_balance — счётчик спинов (не валюта, не торгуется напрямую).
"""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TransactionResource(PyEnum):
    GEMS = "GEMS"
    SPINS = "SPINS"


class TransactionReason(PyEnum):
    WELCOME_SPIN = "WELCOME_SPIN"
    PURCHASE = "PURCHASE"
    ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT"
    SPIN = "SPIN"
    DAILY_FREE_SPIN = "DAILY_FREE_SPIN"
    TELEGRAM_STARS_PURCHASE = "TELEGRAM_STARS_PURCHASE"  # пополнение GEMS за Telegram Stars
    DUPLICATE_REFUND = "DUPLICATE_REFUND"  # возврат GEMS за дубликат медиа


class UserWallet(Base):
    __tablename__ = "user_wallets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    gems_balance: Mapped[int] = mapped_column(Integer, default=0)
    spins_balance: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("gems_balance >= 0", name="ck_user_wallets_gems_non_negative"),
        CheckConstraint("spins_balance >= 0", name="ck_user_wallets_spins_non_negative"),
    )

    user: Mapped["User"] = relationship(back_populates="wallet")  # type: ignore[name-defined]
    transactions: Mapped[list["WalletTransaction"]] = relationship(
        back_populates="wallet", cascade="all, delete-orphan"
    )


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("user_wallets.id", ondelete="CASCADE"), index=True
    )
    resource: Mapped[TransactionResource] = mapped_column(
        SAEnum(TransactionResource, values_callable=lambda x: [e.value for e in x])
    )
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[TransactionReason] = mapped_column(
        SAEnum(TransactionReason, values_callable=lambda x: [e.value for e in x])
    )
    performed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    wallet: Mapped["UserWallet"] = relationship(back_populates="transactions")


class GemPackage(Base):
    """Пакет GEMS, доступный для покупки за Telegram Stars."""

    __tablename__ = "gem_packages"

    __table_args__ = (
        CheckConstraint("gems_amount > 0", name="ck_gem_packages_gems_positive"),
        CheckConstraint("price_stars > 0", name="ck_gem_packages_price_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    gems_amount: Mapped[int] = mapped_column(Integer)  # сколько GEMS в пакете
    price_stars: Mapped[int] = mapped_column(Integer)  # цена в Telegram Stars (XTR)
    is_active: Mapped[bool] = mapped_column(default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GemPurchase(Base):
    """История покупок GEMS за Telegram Stars."""

    __tablename__ = "gem_purchases"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    package_id: Mapped[int | None] = mapped_column(ForeignKey("gem_packages.id"), nullable=True)
    gems_added: Mapped[int] = mapped_column(Integer)
    price_stars: Mapped[int] = mapped_column(Integer)  # фактически уплачено Stars
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)
