import io
from PIL import Image

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db import get_session
from app.models.content import MediaAsset, MediaType, ContentItemMedia, FileRole
from app.models.content import ContentItem

router = APIRouter(prefix="/api/v1/admin", tags=["admin-media"])


async def _get_bot():
    from bot.main import get_bot
    return await get_bot()


@router.get("/media")
async def list_media(
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(MediaAsset).order_by(MediaAsset.uploaded_at.desc()))
    assets = result.scalars().all()
    return {
        "items": [
            {
                "id": a.id,
                "file_type": a.file_type.value,
                "file_size": a.file_size,
                "file_name": a.file_name,
                "width": a.width,
                "height": a.height,
                "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None,
            }
            for a in assets
        ]
    }


@router.post("/media/upload")
async def upload_media(
    file: UploadFile = File(...),
    content_item_id: int = Form(...),
    role: FileRole = FileRole.PREVIEW,
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    content_item = await session.get(ContentItem, content_item_id)
    if not content_item:
        raise HTTPException(status_code=404, detail="Content item not found")

    content = await file.read()
    file_type = MediaType.PHOTO if file.content_type and file.content_type.startswith("image") else MediaType.VIDEO

    if file_type == MediaType.PHOTO:
        img = Image.open(io.BytesIO(content))
        img.thumbnail((1280, 1280))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        content = buf.getvalue()
        width, height = img.size
        mime_type = "image/jpeg"
    else:
        width = height = None
        mime_type = file.content_type or "video/mp4"

    from aiogram import Bot
    from app.config import settings

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

    if file_type == MediaType.PHOTO:
        sent = await bot.send_photo(
            chat_id=settings.CHANNEL_ID,
            photo=content,
            caption=f"Upload: {file.filename}",
        )
        telegram_file_id = sent.photo[-1].file_id
        telegram_file_unique_id = sent.photo[-1].file_unique_id
    else:
        sent = await bot.send_video(
            chat_id=settings.CHANNEL_ID,
            video=content,
            caption=f"Upload: {file.filename}",
        )
        telegram_file_id = sent.video.file_id
        telegram_file_unique_id = sent.video.file_unique_id

    asset = MediaAsset(
        file_type=file_type,
        telegram_file_id=telegram_file_id,
        telegram_file_unique_id=telegram_file_unique_id,
        mime_type=mime_type,
        file_size=len(content),
        file_name=file.filename,
        width=width,
        height=height,
    )
    session.add(asset)
    await session.flush()

    link = ContentItemMedia(
        content_item_id=content_item_id,
        media_asset_id=asset.id,
        role=role,
    )
    session.add(link)
    await session.commit()

    return {"media_asset_id": asset.id, "content_item_id": content_item_id}
