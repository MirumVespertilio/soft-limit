from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db import get_session
from app.models.content import ContentItem, ContentStatus, MediaType
from app.models.content import ContentItemMedia, MediaAsset, FileRole
from app.models.wheel import WheelSegment
from app.models.welcome import WelcomeRewardItem

router = APIRouter(prefix="/api/v1/admin", tags=["admin-content"])


class ContentCreateRequest(BaseModel):
    title: str
    description: str | None = None
    media_type: MediaType


class ContentUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: ContentStatus | None = None
    media_type: MediaType | None = None


@router.get("/content")
async def list_content(
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(ContentItem).order_by(ContentItem.created_at.desc()))
    items = result.scalars().all()
    return {
        "items": [
            {
                "id": c.id,
                "title": c.title,
                "description": c.description,
                "status": c.status.value,
                "media_type": c.media_type.value,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in items
        ]
    }


@router.post("/content")
async def create_content(
    request: ContentCreateRequest,
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    item = ContentItem(
        title=request.title,
        description=request.description,
        media_type=request.media_type,
        status=ContentStatus.DRAFT,
    )
    session.add(item)
    await session.commit()
    return {"id": item.id}


@router.patch("/content/{content_id}")
async def update_content(
    content_id: int,
    request: ContentUpdateRequest,
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(ContentItem, content_id)
    if not item:
        raise HTTPException(status_code=404, detail="Content not found")

    for key, value in request.model_dump(exclude_unset=True).items():
        setattr(item, key, value)

    if request.status == ContentStatus.PUBLISHED:
        from app.models.wheel import Wheel
        wheel_result = await session.execute(
            select(Wheel).where(Wheel.status == "active").limit(1)
        )
        wheel = wheel_result.scalars().first()
        if not wheel:
            raise HTTPException(status_code=400, detail="No active wheel")

        in_wheel = await session.execute(
            select(WheelSegment).where(
                WheelSegment.content_item_id == content_id,
                WheelSegment.wheel_id == wheel.id,
                WheelSegment.is_active == True,
            ).limit(1)
        )
        if not in_wheel.scalars().first():
            raise HTTPException(
                status_code=400,
                detail="Cannot publish: content not linked to active wheel segment",
            )

    await session.commit()
    return {"id": item.id}
