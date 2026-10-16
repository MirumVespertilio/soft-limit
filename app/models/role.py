"""Модель роли пользователя.

Роли хранятся в таблице user_roles.
Возможные значения: 'user' (обычный игрок), 'admin' (владелец модели).
Архитектурно предусмотрено масштабирование под будущий multi-tenant SaaS.
"""
from enum import Enum as PyEnum

from sqlalchemy import Enum as SAEnum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class RoleType(PyEnum):
    """Допустимые роли пользователей в системе."""
    USER = "user"
    ADMIN = "admin"


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[RoleType] = mapped_column(
        SAEnum(RoleType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=RoleType.USER,
    )

    __table_args__ = (
        # Один пользователь — одна запись (при необходимости расширить до many-to-many)
        UniqueConstraint("user_id", name="uq_user_roles_user_id"),
    )

    user: Mapped["User"] = relationship(back_populates="role")  # type: ignore[name-defined]
