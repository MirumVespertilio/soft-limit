from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import update
from app.models.delivery import MediaDelivery, DeliveryStatus
from app.models.inventory import UserInventory
from app.models.content import ContentItem, ContentItemMedia, MediaAsset, MediaType, FileRole
from app.models.user import User


async def request_delivery(
    session: AsyncSession,
    user_id: int,
    inventory_id: int,
) -> MediaDelivery:
    from sqlalchemy.exc import IntegrityError

    result = await session.execute(
        select(MediaDelivery).where(MediaDelivery.inventory_id == inventory_id)
    )
    delivery = result.scalar_one_or_none()
    if delivery:
        if delivery.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        return delivery

    inv_result = await session.execute(
        select(ContentItemMedia)
        .join(UserInventory, UserInventory.content_item_id == ContentItemMedia.content_item_id)
        .where(
            UserInventory.id == inventory_id,
            UserInventory.user_id == user_id,
        )
    )
    media_links = inv_result.scalars().all()

    original_link = next((m for m in media_links if m.role == FileRole.ORIGINAL), None)
    if not original_link:
        original_link = next((m for m in media_links if m.role == FileRole.MAIN), None)
    if not original_link:
        raise ValueError("No original media found for this inventory item")

    delivery = MediaDelivery(
        user_id=user_id,
        media_asset_id=original_link.media_asset_id,
        inventory_id=inventory_id,
        status=DeliveryStatus.PENDING,
    )
    session.add(delivery)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        result = await session.execute(
            select(MediaDelivery).where(MediaDelivery.inventory_id == inventory_id)
        )
        existing = result.scalar_one_or_none()
        if existing and existing.user_id == user_id:
            return existing
        raise HTTPException(status_code=403, detail="Access denied")
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
    capture_result = await session.execute(
        update(MediaDelivery)
        .where(
            MediaDelivery.id == delivery_id,
            MediaDelivery.status.in_([DeliveryStatus.PENDING, DeliveryStatus.FAILED]),
        )
        .values(status=DeliveryStatus.PROCESSING)
    )
    if capture_result.rowcount == 0:
        existing = await session.get(MediaDelivery, delivery_id)
        if existing and existing.status == DeliveryStatus.SENT:
            return existing
        return existing

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
        if asset.file_type == MediaType.VIDEO:
            await bot.send_video(
                chat_id=user.telegram_id,
                video=asset.telegram_file_id,
            )
        else:
            await bot.send_document(
                chat_id=user.telegram_id,
                document=asset.telegram_file_id,
            )
        delivery.status = DeliveryStatus.SENT
    except Exception as e:
        delivery.status = DeliveryStatus.FAILED
        delivery.last_error = str(e)

    await session.flush()
    return delivery
