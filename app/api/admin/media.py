import io
from PIL import Image
from aiogram.types import BufferedInputFile

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select, delete
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
    if role == FileRole.PREVIEW and file_type != MediaType.PHOTO:
        raise HTTPException(status_code=400, detail="Preview must be an image; upload a video as Main")

    from app.config import settings
    from app.telegram import create_telegram_bot

    bot = create_telegram_bot()

    try:
        if file_type == MediaType.PHOTO:
            img = Image.open(io.BytesIO(content))
            orig_width, orig_height = img.size
            orig_format = img.format or "JPEG"
            orig_mime = f"image/{orig_format.lower()}" if orig_format != "JPEG" else "image/jpeg"

            orig_input = BufferedInputFile(content, filename=file.filename)
            sent = await bot.send_document(
                chat_id=settings.CHANNEL_ID,
                document=orig_input,
                caption=f"Original: {file.filename}",
            )
            telegram_file_id = sent.document.file_id
            telegram_file_unique_id = sent.document.file_unique_id

            if role != FileRole.PREVIEW:
                preview_img = img.copy()
                preview_img.thumbnail((320, 320))
                if preview_img.mode in ("RGBA", "LA", "P"):
                    background = Image.new("RGB", preview_img.size, (255, 255, 255))
                    if preview_img.mode == "P":
                        preview_img = preview_img.convert("RGBA")
                    if preview_img.mode in ("RGBA", "LA"):
                        background.paste(preview_img, mask=preview_img.split()[-1])
                        preview_img = background
                else:
                    preview_img = preview_img.convert("RGB")

                preview_buf = io.BytesIO()
                preview_img.save(preview_buf, format="JPEG", quality=85)
                preview_bytes = preview_buf.getvalue()
                prev_width, prev_height = preview_img.size

                prev_input = BufferedInputFile(preview_bytes, filename=f"preview_{file.filename}")
                prev_sent = await bot.send_photo(
                    chat_id=settings.CHANNEL_ID,
                    photo=prev_input,
                    caption=f"Preview: {file.filename}",
                )
                prev_file_id = prev_sent.photo[-1].file_id
                prev_file_unique_id = prev_sent.photo[-1].file_unique_id
                prev_mime = "image/jpeg"
            else:
                preview_bytes = b""
                prev_file_id = prev_file_unique_id = None
                prev_width = prev_height = None
                prev_mime = None
        else:
            orig_input = BufferedInputFile(content, filename=file.filename)
            sent = await bot.send_video(
                chat_id=settings.CHANNEL_ID,
                video=orig_input,
                caption=f"Upload: {file.filename}",
            )
            telegram_file_id = sent.video.file_id
            telegram_file_unique_id = sent.video.file_unique_id
            orig_mime = file.content_type or "video/mp4"
            orig_width = orig_height = None
            prev_file_id = prev_file_unique_id = None
            prev_width = prev_height = None
            prev_mime = None
    finally:
        await bot.session.close()

    asset = MediaAsset(
        file_type=file_type,
        telegram_file_id=telegram_file_id,
        telegram_file_unique_id=telegram_file_unique_id,
        mime_type=orig_mime,
        file_size=len(content),
        file_name=file.filename,
        width=orig_width,
        height=orig_height,
    )
    session.add(asset)
    await session.flush()

    # Always retain the uploaded file as ORIGINAL so delivery can send it.
    # A PREVIEW upload is display-only: never mark that same asset ORIGINAL,
    # otherwise the delivery flow could hand the preview to the user.
    if role == FileRole.PREVIEW:
        # Remove legacy ORIGINAL links to the old preview assets before deleting
        # their PREVIEW links. Earlier app versions incorrectly assigned both roles.
        old_preview_result = await session.execute(
            select(ContentItemMedia.media_asset_id).where(
                ContentItemMedia.content_item_id == content_item_id,
                ContentItemMedia.role == FileRole.PREVIEW,
            )
        )
        old_preview_asset_ids = set(old_preview_result.scalars().all())
        if old_preview_asset_ids:
            await session.execute(
                delete(ContentItemMedia).where(
                    ContentItemMedia.content_item_id == content_item_id,
                    ContentItemMedia.role == FileRole.ORIGINAL,
                    ContentItemMedia.media_asset_id.in_(old_preview_asset_ids),
                )
            )
        await session.execute(
            delete(ContentItemMedia).where(
                ContentItemMedia.content_item_id == content_item_id,
                ContentItemMedia.role == FileRole.PREVIEW,
            )
        )
        session.add(ContentItemMedia(
            content_item_id=content_item_id,
            media_asset_id=asset.id,
            role=FileRole.PREVIEW,
            position=0,
        ))
    else:
        session.add(ContentItemMedia(
            content_item_id=content_item_id,
            media_asset_id=asset.id,
            role=FileRole.ORIGINAL,
        ))
        if role == FileRole.MAIN:
            await session.execute(
                delete(ContentItemMedia).where(
                    ContentItemMedia.content_item_id == content_item_id,
                    ContentItemMedia.role == FileRole.MAIN,
                )
            )
            session.add(ContentItemMedia(
                content_item_id=content_item_id,
                media_asset_id=asset.id,
                role=FileRole.MAIN,
                position=0,
            ))

    if file_type == MediaType.PHOTO and prev_file_id and role != FileRole.PREVIEW:
        existing_preview = await session.execute(
            select(ContentItemMedia.id).where(
                ContentItemMedia.content_item_id == content_item_id,
                ContentItemMedia.role == FileRole.PREVIEW,
            ).limit(1)
        )
        if not existing_preview.scalars().first():
            preview_asset = MediaAsset(
                file_type=MediaType.PHOTO,
                telegram_file_id=prev_file_id,
                telegram_file_unique_id=prev_file_unique_id,
                mime_type=prev_mime,
                file_size=len(preview_bytes),
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
