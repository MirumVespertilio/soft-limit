from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class MediaDelivery(Base):
    __tablename__ = "media_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    media_asset_id: Mapped[int] = mapped_column(ForeignKey("media_assets.id"))
    inventory_id: Mapped[int | None] = mapped_column(ForeignKey("user_inventory.id"), nullable=True)
    status: Mapped[DeliveryStatus] = mapped_column(Enum("pending", "sent", "failed", name="deliverystatus"), default=DeliveryStatus.PENDING)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
