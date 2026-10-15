from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class WheelStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Wheel(Base):
    __tablename__ = "wheels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[WheelStatus] = mapped_column(Enum("active", "inactive", name="wheelstatus"), default=WheelStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    segments: Mapped[list["WheelSegment"]] = relationship(back_populates="wheel", cascade="all, delete-orphan")


class WheelSegment(Base):
    __tablename__ = "wheel_segments"
    __table_args__ = (UniqueConstraint("wheel_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    wheel_id: Mapped[int] = mapped_column(ForeignKey("wheels.id", ondelete="CASCADE"), index=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id"))
    label: Mapped[str] = mapped_column(String(64))
    weight: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer)

    wheel: Mapped["Wheel"] = relationship(back_populates="segments")
