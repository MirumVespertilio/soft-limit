from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.db import get_session
from app.models.wheel import Wheel, WheelSegment, WheelStatus
from app.models.content import ContentItem, ContentItemMedia, FileRole, ContentStatus
from app.services.spin import get_active_wheel_for_model

router = APIRouter(prefix="/api/v1", tags=["wheel"])


@router.get("/wheel")
async def get_wheel(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    wheel = await get_active_wheel_for_model(session, current_user.model_id)
    if wheel is None:
        wheel_result = await session.execute(
            select(Wheel).where(Wheel.status == WheelStatus.ACTIVE).order_by(Wheel.id)
        )
        wheel = wheel_result.scalars().first()

    if not wheel:
        return {"wheel": None, "segments": []}

    segments_result = await session.execute(
        select(WheelSegment, ContentItem)
        .outerjoin(ContentItem, WheelSegment.content_item_id == ContentItem.id)
        .where(
            WheelSegment.wheel_id == wheel.id,
            WheelSegment.is_active == True,  # noqa: E712
        )
        .order_by(WheelSegment.position)
    )

    segments = []
    for seg, item in segments_result.all():
        if seg.content_item_id is not None and (
            item is None or item.status != ContentStatus.PUBLISHED
        ):
            continue

        preview_media_id = None
        if item is not None:
            preview_result = await session.execute(
                select(ContentItemMedia)
                .where(
                    ContentItemMedia.content_item_id == item.id,
                    ContentItemMedia.role == FileRole.PREVIEW,
                )
                .order_by(ContentItemMedia.position)
            )
            preview = preview_result.scalars().first()
            preview_media_id = preview.media_asset_id if preview else None

        segments.append({
            "segment_id": seg.id,
            "position": seg.position,
            "label": seg.label,
            "weight": seg.weight,
            "content_item_id": seg.content_item_id,
            "title": item.title if item else None,
            "description": item.description if item else None,
            "media_type": item.media_type.value if item else None,
            "rarity": item.rarity.value if item else None,
            "reward_type": seg.reward_type.value,
            "reward_gems": seg.reward_gems,
            "reward_spins": seg.reward_spins,
            "preview_media_id": preview_media_id,
        })

    return {
        "wheel": {"id": wheel.id, "name": wheel.name, "model_id": wheel.model_id},
        "segments": segments,
    }
