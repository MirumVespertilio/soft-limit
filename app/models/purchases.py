from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SpinPackage(Base):
    __tablename__ = "spin_packages"
    __table_args__ = (
        CheckConstraint("spins_count > 0", name="ck_spin_packages_spins_positive"),
        CheckConstraint("price_gems >= 0", name="ck_spin_packages_price_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    spins_count: Mapped[int] = mapped_column(Integer)
    price_gems: Mapped[int] = mapped_column(Integer)
    price_stars: Mapped[int] = mapped_column(Integer, default=0)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SpinPurchase(Base):
    __tablename__ = "spin_purchases"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("spin_packages.id"))
    price_gems: Mapped[int] = mapped_column(Integer)
    cost_stars: Mapped[int] = mapped_column(Integer, default=0)
    spins_added: Mapped[int] = mapped_column(Integer)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)
