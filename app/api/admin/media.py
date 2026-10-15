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

MAX_FILE_SIZE = 50 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4"}


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
    role: FileRole = Form(...),
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    content_item = await session.get(ContentItem, content_item_id)
    if not content_item:
        raise HTTPException(status_code=404, detail="Content item not found")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")

    is_image = file.content_type in ALLOWED_IMAGE_TYPES
    is_video = file.content_type in ALLOWED_VIDEO_TYPES
    if not is_image and not is_video:
        raise HTTPException(status_code=415, detail="Unsupported file type")

    file_type = MediaType.PHOTO if is_image else MediaType.VIDEO

    from aiogram import Bot
    from app.config import settings

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

    try:
        if file_type == MediaType.PHOTO:
            sent = await bot.send_photo(
                chat_id=settings.CHANNEL_ID,
                photo=content,
                caption=f"Upload: {file.filename}",
            )
            telegram_file_id = sent.photo[-1].file_id
            telegram_file_unique_id = sent.photo[-1].file_unique_id
            orig_width, orig_height = Image.open(io.BytesIO(content)).size

            img = Image.open(io.BytesIO(content))
            img.thumbnail((320, 320))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            preview_content = buf.getvalue()
            prev_width, prev_height = img.size

            prev_sent = await bot.send_photo(
                chat_id=settings.CHANNEL_ID,
                photo=preview_content,
                caption=f"Preview: {file.filename}",
            )
            prev_file_id = prev_sent.photo[-1].file_id
            prev_file_unique_id = prev_sent.photo[-1].file_unique_id
        else:
            sent = await bot.send_video(
                chat_id=settings.CHANNEL_ID,
                video=content,
                caption=f"Upload: {file.filename}",
            )
            telegram_file_id = sent.video.file_id
            telegram_file_unique_id = sent.video.file_unique_id
            orig_width = orig_height = None
            prev_file_id = prev_file_unique_id = None
            prev_width = prev_height = None
    finally:
        await bot.session.close()

    asset = MediaAsset(
        file_type=file_type,
        telegram_file_id=telegram_file_id,
        telegram_file_unique_id=telegram_file_unique_id,
        mime_type=file.content_type,
        file_size=len(content),
        file_name=file.filename,
        width=orig_width,
        height=orig_height,
    )
    session.add(asset)
    await session.flush()

    link = ContentItemMedia(
        content_item_id=content_item_id,
        media_asset_id=asset.id,
        role=FileRole.ORIGINAL if role == FileRole.MAIN else role,
    )
    session.add(link)

    if file_type == MediaType.PHOTO and prev_file_id:
        preview_asset = MediaAsset(
            file_type=MediaType.PHOTO,
            telegram_file_id=prev_file_id,
            telegram_file_unique_id=prev_file_unique_id,
            mime_type="image/jpeg",
            file_size=len(preview_content),
            file_name=f"preview_{file.filename}",
            width=prev_width,
            height=prev_height,
        )
        session.add(preview_asset)
        await session.flush()

        preview_link = ContentItemMedia(
            content_item_id=content_item_id,
            media_asset_id=preview_asset.id,
            role=FileRole.PREVIEW,
        )
        session.add(preview_link)

    await session.commit()

    return {"media_asset_id": asset.id, "content_item_id": content_item_id}
