from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SpinType(PyEnum):
    WELCOME = "welcome"
    STANDARD = "standard"


class Spin(Base):
    __tablename__ = "spins"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    wheel_id: Mapped[int | None] = mapped_column(ForeignKey("wheels.id"), nullable=True)
    spin_type: Mapped[SpinType] = mapped_column(SAEnum(SpinType, values_callable=lambda x: [e.value for e in x]))
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id"))
    segment_id: Mapped[int | None] = mapped_column(ForeignKey("wheel_segments.id"), nullable=True)
    cost_spins: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "idempotency_key"),)
