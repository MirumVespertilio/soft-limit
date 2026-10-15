from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delivery import MediaDelivery, DeliveryStatus
from app.models.inventory import UserInventory
from app.models.content import ContentItem, ContentItemMedia, MediaAsset, MediaType
from app.models.user import User


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


async def execute_delivery(
    session: AsyncSession,
    bot,
    delivery_id: int,
) -> MediaDelivery:
    delivery = await session.get(MediaDelivery, delivery_id)
    if not delivery:
        raise ValueError("Delivery not found")

    asset = await session.get(MediaAsset, delivery.media_asset_id)
    if not asset:
        raise ValueError("Media asset not found")

    user_result = await session.execute(select(User).where(User.id == delivery.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise ValueError("User not found")

    delivery.attempts += 1
    delivery.last_attempt_at = datetime.now(timezone.utc)

    try:
        if asset.file_type == MediaType.PHOTO:
            await bot.send_photo(
                chat_id=user.telegram_id,
                photo=asset.telegram_file_id,
            )
        elif asset.file_type == MediaType.VIDEO:
            await bot.send_video(
                chat_id=user.telegram_id,
                video=asset.telegram_file_id,
            )
        delivery.status = DeliveryStatus.SENT
    except Exception as e:
        delivery.status = DeliveryStatus.FAILED
        delivery.last_error = str(e)

    await session.flush()
    return delivery
