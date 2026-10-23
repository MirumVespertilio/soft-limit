from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItemMedia, FileRole


async def get_first_media_asset_id(
    session: AsyncSession,
    content_item_id: int,
    role: FileRole,
) -> int | None:
    """Первый media_asset_id контент-айтема с заданной ролью (по position)."""
    result = await session.execute(
        select(ContentItemMedia.media_asset_id)
        .where(
            ContentItemMedia.content_item_id == content_item_id,
            ContentItemMedia.role == role,
        )
        .order_by(ContentItemMedia.position)
        .limit(1)
    )
    return result.scalars().first()


async def get_preview_media_id(
    session: AsyncSession,
    content_item_id: int,
) -> int | None:
    """ID превью-ассета контент-айтема (role=PREVIEW) или None."""
    return await get_first_media_asset_id(session, content_item_id, FileRole.PREVIEW)
