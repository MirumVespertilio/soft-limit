from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db import get_session
from app.models.wheel import Wheel, WheelSegment
from app.models.content import ContentItem, ContentItemMedia, FileRole
from app.models.content import ContentStatus

router = APIRouter(prefix="/api/v1", tags=["wheel"])


@router.get("/wheel")
async def get_wheel(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    wheel_result = await session.execute(
        select(Wheel).where(Wheel.status == "active").order_by(Wheel.id)
    )
    wheel = wheel_result.scalars().first()
    if not wheel:
        return {"wheel": None, "segments": []}

    segments_result = await session.execute(
        select(WheelSegment, ContentItem)
        .join(ContentItem, WheelSegment.content_item_id == ContentItem.id)
        .where(
            WheelSegment.wheel_id == wheel.id,
            WheelSegment.is_active == True,
            ContentItem.status == ContentStatus.PUBLISHED,
        )
        .order_by(WheelSegment.position)
    )

    segments = []
    for seg, item in segments_result.all():
        preview_result = await session.execute(
            select(ContentItemMedia)
            .where(
                ContentItemMedia.content_item_id == item.id,
                ContentItemMedia.role == FileRole.PREVIEW,
            )
            .order_by(ContentItemMedia.position)
        )
        preview = preview_result.scalars().first()
        segments.append({
            "segment_id": seg.id,
            "label": seg.label,
            "weight": seg.weight,
            "content_item_id": item.id,
            "title": item.title,
            "description": item.description,
            "media_type": item.media_type.value,
            "preview_media_id": preview.media_asset_id if preview else None,
        })

    return {"wheel": {"id": wheel.id, "name": wheel.name}, "segments": segments}
