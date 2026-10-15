import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db import get_session
from app.models.user import User
from app.models.wheel import WheelSegment
from app.models.spin import Spin, SpinType
from app.models.content import ContentItem, ContentStatus
from app.models.inventory import UserInventory, InventorySource
from app.models.wallet import TransactionResource, TransactionReason
from app.services.wallet import adjust_balance, InsufficientBalanceError, get_wallet_by_user_id
from app.services.wheel import get_active_wheel, get_active_segments, weighted_random_choice
from app.models.welcome import WelcomeRewardItem

router = APIRouter(prefix="/api/v1", tags=["spin"])


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
        return SpinResponse(
            spin_id=existing_spin.id,
            content_item_id=item.id,
            segment_id=existing_spin.segment_id,
            title=item.title,
            description=item.description,
            media_type=item.media_type.value,
            is_welcome=existing_spin.spin_type == SpinType.WELCOME,
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
            user_id=user_id,
            resource=TransactionResource.SPINS,
            amount=-1,
            reason=TransactionReason.SPIN,
        )
    except InsufficientBalanceError:
        raise HTTPException(status_code=400, detail="No spins available")

    spin = Spin(
        user_id=user_id,
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
        user_id=user_id,
        content_item_id=chosen_item.id,
        source=InventorySource.SPIN,
        reference_id=spin.id,
    )
    session.add(inventory_item)

    if is_welcome:
        user.welcome_spin_used_at = datetime.now(timezone.utc)

    await session.commit()

    return SpinResponse(
        spin_id=spin.id,
        content_item_id=chosen_item.id,
        segment_id=spin.segment_id,
        title=chosen_item.title,
        description=chosen_item.description,
        media_type=chosen_item.media_type.value,
        is_welcome=is_welcome,
    )
