from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InventorySource(PyEnum):
    SPIN = "spin"
    ORDER = "order"
    ADMIN_GRANT = "admin_grant"


class UserInventory(Base):
    __tablename__ = "user_inventory"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id"))
    source: Mapped[InventorySource] = mapped_column(
        SAEnum(InventorySource, values_callable=lambda x: [e.value for e in x])
    )
    reference_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "content_item_id", "source", "reference_id"),)
