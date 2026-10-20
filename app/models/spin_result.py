from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.content import Rarity


class SpinResult(Base):
    """Результат конкретного спина (колесо или медиа-слот)."""

    __tablename__ = "spin_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    spin_id: Mapped[int] = mapped_column(
        ForeignKey("spins.id", ondelete="CASCADE"), unique=True, index=True
    )
    content_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("content_items.id"), nullable=True
    )
    reward_gems: Mapped[int] = mapped_column(Integer, default=0)
    reward_spins: Mapped[int] = mapped_column(Integer, default=0)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    rarity: Mapped[Rarity | None] = mapped_column(
        SAEnum(Rarity, values_callable=lambda x: [e.value for e in x]), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    spin: Mapped["Spin"] = relationship(back_populates="result")  # type: ignore[name-defined]
