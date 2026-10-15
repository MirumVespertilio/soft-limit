from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db import get_session
from app.services.delivery import request_delivery, get_delivery_status, execute_delivery
from app.models.delivery import DeliveryStatus

router = APIRouter(prefix="/api/v1", tags=["delivery"])


@router.post("/inventory/{inventory_id}/deliver")
async def deliver_item(
    inventory_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        delivery = await request_delivery(session, user_id, inventory_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    from aiogram import Bot
    from app.config import settings
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

    delivery = await execute_delivery(session, bot, delivery.id)
    await session.commit()

    return {
        "delivery_id": delivery.id,
        "status": delivery.status.value,
    }


@router.get("/inventory/{inventory_id}/delivery-status")
async def delivery_status(
    inventory_id: int,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    delivery = await get_delivery_status(session, user_id, inventory_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")

    return {
        "delivery_id": delivery.id,
        "status": delivery.status.value,
        "attempts": delivery.attempts,
        "last_error": delivery.last_error,
        "last_attempt_at": delivery.last_attempt_at.isoformat() if delivery.last_attempt_at else None,
    }
