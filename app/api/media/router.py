from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db import get_session
from app.models.content import MediaAsset, ContentItemMedia, FileRole
from app.models.inventory import UserInventory

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

    inv_result = await session.execute(
        select(UserInventory.id).where(
            UserInventory.user_id == user_id,
            UserInventory.content_item_id == link.content_item_id,
        ).limit(1)
    )
    if not inv_result.scalars().first():
        raise HTTPException(status_code=403, detail="Access denied")

    asset = await session.get(MediaAsset, media_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Media not found")

    from aiogram import Bot
    from app.config import settings

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    try:
        file = await bot.get_file(asset.telegram_file_id)
        content = await bot.download_file(file.file_path)
        return Response(content=content, media_type=asset.mime_type or "image/jpeg")
    finally:
        await bot.session.close()
