from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    welcome_spin_granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    welcome_spin_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    wallet: Mapped["UserWallet"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
