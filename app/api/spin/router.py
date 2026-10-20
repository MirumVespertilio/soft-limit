import random
from datetime import datetime, timezone

from aiogram.types import LabeledPrice
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_current_user_id
from app.db import get_session
from app.models.user import User
from app.models.wheel import WheelSegment
from app.models.spin import Spin, SpinType
from app.models.content import ContentItem, ContentStatus
from app.models.inventory import UserInventory, InventorySource
from app.models.wallet import TransactionResource, TransactionReason
from app.models.model import Model
from app.services.wallet import adjust_balance, InsufficientBalanceError, get_wallet_by_user_id
from app.services.wheel import get_active_wheel, get_active_segments, weighted_random_choice
from app.models.welcome import WelcomeRewardItem
from app.services.spin import (
    NoActiveWheel,
    NoContentAvailable,
    InsufficientGems,
    InsufficientSpinBalance,
    MediaSpinNotConfigured,
    complete_media_spin_with_stars,
    daily_free_spin_status,
    get_spin_by_id,
    get_spin_history,
    grant_daily_free_spin,
    perform_media_spin,
    perform_wheel_spin,
    send_media_to_chat,
)
from app.telegram import create_telegram_bot

router = APIRouter(prefix="/api/v1", tags=["spin"])


def _require_model_id(current_user: CurrentUser) -> int:
    if current_user.model_id is None:
        raise HTTPException(status_code=400, detail="model_id is required")
    return current_user.model_id


# ==============================================================================
# Legacy endpoint (welcome + weighted standard wheel)
# ==============================================================================


class SpinRequest(BaseModel):
    idempotency_key: str


class SpinResponse(BaseModel):
    spin_id: int
    content_item_id: int
    segment_id: int | None
    title: str
    description: str | None
    media_type: str
    is_welcome: bool
    preview_media_id: int | None = None


@router.post("/spins", response_model=SpinResponse)
async def create_spin(
    request: SpinRequest,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    idem_key = request.idempotency_key

    existing = await session.execute(
        select(Spin).where(Spin.user_id == user_id, Spin.idempotency_key == idem_key)
    )
    existing_spin = existing.scalar_one_or_none()
    if existing_spin:
        item = await session.get(ContentItem, existing_spin.content_item_id)
        from app.models.content import ContentItemMedia, FileRole
        preview_result = await session.execute(
            select(ContentItemMedia.media_asset_id)
            .where(
                ContentItemMedia.content_item_id == item.id,
                ContentItemMedia.role == FileRole.PREVIEW,
            ).limit(1)
        )
        preview_media_id = preview_result.scalars().first()
        return SpinResponse(
            spin_id=existing_spin.id,
            content_item_id=item.id,
            segment_id=existing_spin.segment_id,
            title=item.title,
            description=item.description,
            media_type=item.media_type.value,
            is_welcome=existing_spin.spin_type == SpinType.WELCOME,
            preview_media_id=preview_media_id,
        )

    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    is_welcome = user.welcome_spin_used_at is None

    if is_welcome:
        wheel = await get_active_wheel(session)
        if not wheel:
            raise HTTPException(status_code=400, detail="No active wheel")

        pool_result = await session.execute(
            select(WelcomeRewardItem, ContentItem)
            .join(ContentItem, WelcomeRewardItem.content_item_id == ContentItem.id)
            .join(WheelSegment, WheelSegment.content_item_id == ContentItem.id)
            .where(
                WheelSegment.wheel_id == wheel.id,
                WheelSegment.is_active == True,
                ContentItem.status == ContentStatus.PUBLISHED,
            )
            .order_by(WelcomeRewardItem.position)
            .distinct()
        )
        pool = pool_result.all()
        if not pool:
            raise HTTPException(status_code=400, detail="No welcome rewards configured")
        chosen_item = random.choice(pool)[1]
        segment = None
        spin_type = SpinType.WELCOME
    else:
        wheel = await get_active_wheel(session)
        if not wheel:
            raise HTTPException(status_code=400, detail="No active wheel")
        segments = await get_active_segments(session, wheel.id)
        if not segments:
            raise HTTPException(status_code=400, detail="No active segments")
        chosen_segment = weighted_random_choice(segments)
        chosen_item = await session.get(ContentItem, chosen_segment.content_item_id)
        segment = chosen_segment
        spin_type = SpinType.STANDARD

    try:
        await adjust_balance(
            session=session,
            user_id=user.id,
            resource=TransactionResource.SPINS,
            amount=-1,
            reason=TransactionReason.SPIN,
        )
    except InsufficientBalanceError:
        raise HTTPException(status_code=400, detail="No spins available")

    spin = Spin(
        user_id=user.id,
        wheel_id=None if is_welcome else segment.wheel_id,
        spin_type=spin_type,
        content_item_id=chosen_item.id,
        segment_id=None if is_welcome else segment.id,
        cost_spins=1,
        idempotency_key=idem_key,
    )
    session.add(spin)
    await session.flush()

    inventory_item = UserInventory(
        user_id=user.id,
        content_item_id=chosen_item.id,
        source=InventorySource.SPIN,
        reference_id=spin.id,
    )
    session.add(inventory_item)

    if is_welcome:
        user.welcome_spin_used_at = datetime.now(timezone.utc)

    await session.commit()

    from app.models.content import ContentItemMedia, FileRole
    preview_result = await session.execute(
        select(ContentItemMedia.media_asset_id)
        .where(
            ContentItemMedia.content_item_id == chosen_item.id,
            ContentItemMedia.role == FileRole.PREVIEW,
        ).limit(1)
    )
    preview_media_id = preview_result.scalars().first()

    return SpinResponse(
        spin_id=spin.id,
        content_item_id=chosen_item.id,
        segment_id=spin.segment_id,
        title=chosen_item.title,
        description=chosen_item.description,
        media_type=chosen_item.media_type.value,
        is_welcome=is_welcome,
        preview_media_id=preview_media_id,
    )


# ==============================================================================
# Бонусное колесо (wheel)
# ==============================================================================


class WheelSpinRequest(BaseModel):
    idempotency_key: str


@router.post("/spins/wheel")
async def wheel_spin(
    request: WheelSpinRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    model_id = _require_model_id(current_user)
    try:
        response = await perform_wheel_spin(
            session, current_user.id, model_id, request.idempotency_key
        )
    except NoActiveWheel:
        raise HTTPException(status_code=400, detail="No active wheel for this model")
    except InsufficientSpinBalance:
        raise HTTPException(status_code=400, detail="No spins available")

    await session.commit()
    return response


@router.post("/spins/daily-free")
async def daily_free_spin(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await grant_daily_free_spin(session, current_user.id)
    except ValueError:
        raise HTTPException(status_code=404, detail="User not found")


@router.get("/spins/daily-free/status")
async def daily_free_spin_status(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await daily_free_spin_status(session, current_user.id)
    except ValueError:
        raise HTTPException(status_code=404, detail="User not found")


@router.get("/spins/history/wheel")
async def wheel_history(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
):
    items = await get_spin_history(session, current_user.id, SpinType.BONUS, limit, offset)
    return {"items": items}


# ==============================================================================
# Медиа-слоты модели
# ==============================================================================


class MediaSpinRequest(BaseModel):
    idempotency_key: str


class MediaInvoiceRequest(BaseModel):
    model_id: int


class MediaCompleteRequest(BaseModel):
    model_id: int
    idempotency_key: str
    telegram_payment_charge_id: str | None = None


@router.post("/spins/media")
async def media_spin(
    request: MediaSpinRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    model_id = _require_model_id(current_user)
    try:
        response = await perform_media_spin(
            session, current_user.id, model_id, request.idempotency_key
        )
    except MediaSpinNotConfigured:
        raise HTTPException(status_code=400, detail="Media spin is not configured")
    except InsufficientGems:
        raise HTTPException(status_code=400, detail="Insufficient gems")
    except NoContentAvailable:
        raise HTTPException(status_code=400, detail="No content available")

    await session.commit()
    await send_media_to_chat(session, model_id, current_user.id, response["main_media_id"])
    return response


@router.post("/spins/media/invoice-link")
async def create_media_invoice_link(
    request: MediaInvoiceRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    model = await session.get(Model, request.model_id)
    if not model or model.media_spin_price_stars <= 0:
        raise HTTPException(status_code=400, detail="Media spin is not configured")

    payload = f"media_spin_{current_user.id}_{model.id}"
    bot = create_telegram_bot(model.bot_token)
    try:
        invoice_link = await bot.create_invoice_link(
            title="1 Media Spin",
            description="Покупка одного медиа-спина модели",
            payload=payload,
            currency="XTR",
            prices=[LabeledPrice(label="1 Media Spin", amount=model.media_spin_price_stars)],
        )
    finally:
        await bot.session.close()

    return {
        "invoice_link": invoice_link,
        "model_id": model.id,
        "price_stars": model.media_spin_price_stars,
    }


@router.post("/spins/media/complete")
async def complete_media_spin(
    request: MediaCompleteRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        response = await complete_media_spin_with_stars(
            session,
            current_user.id,
            request.model_id,
            request.idempotency_key,
            request.telegram_payment_charge_id,
        )
    except MediaSpinNotConfigured:
        raise HTTPException(status_code=400, detail="Media spin is not configured")
    except NoContentAvailable:
        raise HTTPException(status_code=400, detail="No content available")

    await session.commit()
    await send_media_to_chat(session, request.model_id, current_user.id, response["main_media_id"])
    return response


@router.get("/spins/history/media")
async def media_history(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
):
    items = await get_spin_history(session, current_user.id, SpinType.MEDIA, limit, offset)
    return {"items": items}


@router.get("/spins/{spin_id}")
async def get_spin(
    spin_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await get_spin_by_id(session, current_user.id, spin_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Spin not found")
