from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class SpinType(PyEnum):
    WELCOME = "welcome"
    STANDARD = "standard"
    BONUS = "bonus"  # Ежедневный бесплатный бонусный спин (рулетка/бонусы)
    MEDIA = "media"  # Медиа-слоты модели с выпадением фото/видео


class Spin(Base):
    __tablename__ = "spins"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id"), nullable=True, index=True)
    wheel_id: Mapped[int | None] = mapped_column(ForeignKey("wheels.id"), nullable=True)
    spin_type: Mapped[SpinType] = mapped_column(
        SAEnum(SpinType, values_callable=lambda x: [e.value for e in x]),
        default=SpinType.STANDARD,
    )
    content_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("content_items.id"), nullable=True
    )
    segment_id: Mapped[int | None] = mapped_column(ForeignKey("wheel_segments.id"), nullable=True)
    cost_spins: Mapped[int] = mapped_column(Integer, default=1)
    cost_gems: Mapped[int] = mapped_column(Integer, default=0)
    cost_stars: Mapped[int] = mapped_column(Integer, default=0)
    reward_gems: Mapped[int] = mapped_column(Integer, default=0)
    reward_spins: Mapped[int] = mapped_column(Integer, default=0)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)

    result: Mapped["SpinResult | None"] = relationship(  # type: ignore[name-defined]
        back_populates="spin", uselist=False, cascade="all, delete-orphan"
    )
