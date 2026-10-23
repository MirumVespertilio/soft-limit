from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class FileRole(PyEnum):
    PREVIEW = "preview"
    MAIN = "main"
    ORIGINAL = "original"


class ContentStatus(PyEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DISABLED = "disabled"


class MediaType(PyEnum):
    PHOTO = "photo"
    VIDEO = "video"


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_type: Mapped[MediaType] = mapped_column(
        SAEnum(MediaType, values_callable=lambda x: [e.value for e in x])
    )
    telegram_file_id: Mapped[str] = mapped_column(String(256))
    telegram_file_unique_id: Mapped[str] = mapped_column(String(256))
    mime_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(64), default="telegram")
    processing_state: Mapped[str] = mapped_column(String(32), default="ready")
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    content_links: Mapped[list["ContentItemMedia"]] = relationship(
        back_populates="media", cascade="all, delete-orphan"
    )


class Rarity(PyEnum):
    RARE = "rare"
    LEGENDARY = "legendary"
    MYTHIC = "mythic"
    ETERNAL = "eternal"


# Таблица компенсации дубликатов в GEMS
RARITY_DUPLICATE_REWARD_GEMS = {
    Rarity.RARE: 1,
    Rarity.LEGENDARY: 3,
    Rarity.MYTHIC: 10,
    Rarity.ETERNAL: 50,
}


class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ContentStatus] = mapped_column(
        SAEnum(ContentStatus, values_callable=lambda x: [e.value for e in x]),
        default=ContentStatus.DRAFT,
    )
    media_type: Mapped[MediaType] = mapped_column(
        SAEnum(MediaType, values_callable=lambda x: [e.value for e in x])
    )
    rarity: Mapped[Rarity] = mapped_column(
        SAEnum(Rarity, values_callable=lambda x: [e.value for e in x]),
        default=Rarity.RARE,
        nullable=False,
    )
    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    media: Mapped[list["ContentItemMedia"]] = relationship(
        back_populates="content_item", cascade="all, delete-orphan"
    )


class ContentItemMedia(Base):
    __tablename__ = "content_item_media"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_item_id: Mapped[int] = mapped_column(ForeignKey("content_items.id", ondelete="CASCADE"))
    media_asset_id: Mapped[int] = mapped_column(ForeignKey("media_assets.id", ondelete="CASCADE"))
    role: Mapped[FileRole] = mapped_column(
        SAEnum(FileRole, values_callable=lambda x: [e.value for e in x])
    )
    position: Mapped[int] = mapped_column(Integer, default=0)

    content_item: Mapped["ContentItem"] = relationship(back_populates="media")
    media: Mapped["MediaAsset"] = relationship(back_populates="content_links")
