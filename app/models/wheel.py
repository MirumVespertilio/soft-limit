from datetime import datetime
from enum import Enum as PyEnum

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
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class WheelStatus(PyEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class RewardType(PyEnum):
    """Тип награды сектора бонусного колеса."""

    NONE = "none"
    GEMS = "gems"
    SPINS = "spins"


class Wheel(Base):
    __tablename__ = "wheels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"), nullable=True, index=True
    )
    status: Mapped[WheelStatus] = mapped_column(
        SAEnum(WheelStatus, values_callable=lambda x: [e.value for e in x]),
        default=WheelStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    segments: Mapped[list["WheelSegment"]] = relationship(
        back_populates="wheel", cascade="all, delete-orphan"
    )


class WheelSegment(Base):
    __tablename__ = "wheel_segments"
    __table_args__ = (
        UniqueConstraint("wheel_id", "position"),
        CheckConstraint("weight > 0", name="ck_wheel_segments_weight_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    wheel_id: Mapped[int] = mapped_column(ForeignKey("wheels.id", ondelete="CASCADE"), index=True)
    content_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("content_items.id"), nullable=True
    )
    label: Mapped[str] = mapped_column(String(64))
    weight: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer)
    reward_type: Mapped[RewardType] = mapped_column(
        SAEnum(RewardType, values_callable=lambda x: [e.value for e in x]),
        default=RewardType.NONE,
        nullable=False,
    )
    reward_gems: Mapped[int] = mapped_column(Integer, default=0)
    reward_spins: Mapped[int] = mapped_column(Integer, default=0)

    wheel: Mapped["Wheel"] = relationship(back_populates="segments")
