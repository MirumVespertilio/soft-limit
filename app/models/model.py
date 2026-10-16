"""Модель виртуальной ИИ-модели (SaaS Multi-tenant).

Каждая модель принадлежит владельцу (owner_user_id) и имеет:
- собственный Telegram-бот (bot_token), с которым общается пользователь;
- собственную тему оформления Mini-App (theme_json);
- контент, колеса и спины, привязанные к ней.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Model(Base):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bot_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    theme_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    owner: Mapped["User"] = relationship()  # type: ignore[name-defined]
