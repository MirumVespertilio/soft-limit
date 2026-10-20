from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db import get_session
from app.models.inventory import UserInventory
from app.models.content import ContentItem, ContentItemMedia, FileRole

router = APIRouter(prefix="/api/v1", tags=["inventory"])


@router.get("/inventory")
async def get_inventory(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(UserInventory, ContentItem)
        .join(ContentItem, UserInventory.content_item_id == ContentItem.id)
        .where(UserInventory.user_id == user_id)
        .order_by(UserInventory.created_at.desc())
    )

    items = []
    for inv, item in result.all():
        preview_result = await session.execute(
            select(ContentItemMedia)
            .where(
                ContentItemMedia.content_item_id == item.id,
                ContentItemMedia.role == FileRole.PREVIEW,
            )
            .order_by(ContentItemMedia.position)
        )
        preview = preview_result.scalars().first()
        items.append({
            "inventory_id": inv.id,
            "content_item_id": item.id,
            "title": item.title,
            "description": item.description,
            "media_type": item.media_type.value,
            "rarity": item.rarity.value,
            "source": inv.source.value,
            "preview_media_id": preview.media_asset_id if preview else None,
            "acquired_at": inv.created_at.isoformat(),
        })

    return {"items": items}


@router.get("/inventory/{inventory_id}")
async def get_inventory_item(
    inventory_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(UserInventory, ContentItem)
        .join(ContentItem, UserInventory.content_item_id == ContentItem.id)
        .where(
            UserInventory.id == inventory_id,
            UserInventory.user_id == user_id,
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")

    inv, item = row
    media_result = await session.execute(
        select(ContentItemMedia)
        .where(ContentItemMedia.content_item_id == item.id)
        .order_by(ContentItemMedia.position)
    )
    media = [
        {"media_id": m.media_asset_id, "role": m.role.value}
        for m in media_result.scalars().all()
    ]

    return {
        "inventory_id": inv.id,
        "content_item_id": item.id,
        "title": item.title,
        "description": item.description,
        "media_type": item.media_type.value,
        "source": inv.source.value,
        "media": media,
        "acquired_at": inv.created_at.isoformat(),
    }
