from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delivery import MediaDelivery, DeliveryStatus
from app.models.inventory import UserInventory
from app.models.content import ContentItem, ContentItemMedia
from app.models.content import MediaType


async def request_delivery(
    session: AsyncSession,
    user_id: int,
    inventory_id: int,
) -> MediaDelivery:
    result = await session.execute(
        select(MediaDelivery).where(
            MediaDelivery.inventory_id == inventory_id,
            MediaDelivery.user_id == user_id,
        )
    )
    delivery = result.scalar_one_or_none()
    if delivery:
        return delivery

    inv_result = await session.execute(
        select(ContentItemMedia)
        .join(UserInventory, UserInventory.content_item_id == ContentItemMedia.content_item_id)
        .where(
            UserInventory.id == inventory_id,
            UserInventory.user_id == user_id,
        )
        .order_by(ContentItemMedia.position)
    )
    media_link = inv_result.scalars().first()
    if not media_link:
        raise ValueError("Media not found for this inventory item")

    delivery = MediaDelivery(
        user_id=user_id,
        media_asset_id=media_link.media_asset_id,
        inventory_id=inventory_id,
        status=DeliveryStatus.PENDING,
    )
    session.add(delivery)
    await session.flush()
    return delivery


async def get_delivery_status(
    session: AsyncSession,
    user_id: int,
    inventory_id: int,
) -> MediaDelivery | None:
    result = await session.execute(
        select(MediaDelivery).where(
            MediaDelivery.inventory_id == inventory_id,
            MediaDelivery.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()
