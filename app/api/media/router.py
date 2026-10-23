from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db import get_session
from app.models.content import MediaAsset, ContentItemMedia, FileRole, ContentItem, ContentStatus
from app.models.inventory import UserInventory
from app.models.wheel import Wheel, WheelSegment

router = APIRouter(prefix="/api/v1", tags=["media"])


@router.get("/media/{media_id}/preview")
async def get_preview(
    media_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ContentItemMedia).where(
            ContentItemMedia.media_asset_id == media_id,
            ContentItemMedia.role == FileRole.PREVIEW,
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Preview not found")

    asset = await session.get(MediaAsset, media_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Media not found")

    inv_result = await session.execute(
        select(UserInventory.id)
        .where(
            UserInventory.user_id == user_id,
            UserInventory.content_item_id == link.content_item_id,
        )
        .limit(1)
    )
    has_won = inv_result.scalars().first() is not None

    if not has_won:
        wheel_result = await session.execute(select(Wheel).where(Wheel.status == "active").limit(1))
        wheel = wheel_result.scalars().first()
        if not wheel:
            raise HTTPException(status_code=403, detail="Access denied")

        seg_result = await session.execute(
            select(WheelSegment.id)
            .where(
                WheelSegment.wheel_id == wheel.id,
                WheelSegment.content_item_id == link.content_item_id,
                WheelSegment.is_active.is_(True),
            )
            .limit(1)
        )
        if not seg_result.scalars().first():
            raise HTTPException(status_code=403, detail="Access denied")

        item = await session.get(ContentItem, link.content_item_id)
        if not item or item.status != ContentStatus.PUBLISHED:
            raise HTTPException(status_code=403, detail="Access denied")

    from app.telegram import create_telegram_bot

    bot = create_telegram_bot()
    try:
        file = await bot.get_file(asset.telegram_file_id)
        downloaded = await bot.download_file(file.file_path)
        content = downloaded.read()
        return Response(content=content, media_type=asset.mime_type or "image/jpeg")
    finally:
        await bot.session.close()
