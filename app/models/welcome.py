from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WelcomeRewardItem(Base):
    __tablename__ = "welcome_reward_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id"), unique=True)
    position: Mapped[int] = mapped_column(default=0)
