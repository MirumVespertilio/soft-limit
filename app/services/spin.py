"""Сервис спинов: бонусное колесо и медиа-слоты модели.

Две независимые механики:
- Wheel (бонусное колесо): тратит spins_balance, выдаёт бонусы (ничего/GEMS/спины).
- Media (слоты модели): тратит GEMS или Telegram Stars, выдаёт контент модели с
  редкостью; дубликаты конвертируются в GEMS.
"""

import json
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import (
    ContentItem,
    ContentStatus,
    FileRole,
    MediaAsset,
    MediaType,
    Rarity,
    RARITY_DUPLICATE_REWARD_GEMS,
)
from app.models.model import Model
from app.models.spin import Spin, SpinType
from app.models.spin_result import SpinResult
from app.models.user import User
from app.models.wheel import RewardType, Wheel, WheelSegment, WheelStatus
from app.models.inventory import InventorySource, UserInventory
from app.models.wallet import TransactionReason, TransactionResource
from app.services.wallet import InsufficientBalanceError, adjust_balance, get_wallet_by_user_id
from app.telegram import create_telegram_bot
from app.utils.media import get_first_media_asset_id

DEFAULT_RARITY_WEIGHTS: dict[Rarity, float] = {
    Rarity.RARE: 50,
    Rarity.LEGENDARY: 30,
    Rarity.MYTHIC: 15,
    Rarity.ETERNAL: 5,
}

DAILY_FREE_SPIN_COOLDOWN = timedelta(hours=24)


class SpinServiceError(Exception):
    pass


class InsufficientSpinBalance(SpinServiceError):
    pass


class InsufficientGems(SpinServiceError):
    pass


class NoActiveWheel(SpinServiceError):
    pass


class NoContentAvailable(SpinServiceError):
    pass


class MediaSpinNotConfigured(SpinServiceError):
    pass


def parse_rarity_weights(raw: str | None) -> dict[Rarity, float]:
    if not raw:
        return dict(DEFAULT_RARITY_WEIGHTS)
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return dict(DEFAULT_RARITY_WEIGHTS)
    if not isinstance(data, dict):
        return dict(DEFAULT_RARITY_WEIGHTS)

    weights: dict[Rarity, float] = {}
    for rarity in Rarity:
        value = data.get(rarity.value)
        if value is None:
            value = data.get(rarity.name)
        if isinstance(value, (int, float)) and value > 0:
            weights[rarity] = float(value)
    return weights or dict(DEFAULT_RARITY_WEIGHTS)


async def get_active_wheel_for_model(session: AsyncSession, model_id: int | None) -> Wheel | None:
    if model_id is None:
        return None
    result = await session.execute(
        select(Wheel)
        .where(Wheel.model_id == model_id, Wheel.status == WheelStatus.ACTIVE)
        .order_by(Wheel.id)
    )
    return result.scalars().first()


async def get_active_segments(session: AsyncSession, wheel_id: int) -> list[WheelSegment]:
    result = await session.execute(
        select(WheelSegment)
        .where(WheelSegment.wheel_id == wheel_id, WheelSegment.is_active == True)  # noqa: E712
        .order_by(WheelSegment.position)
    )
    return list(result.scalars().all())


def weighted_segment_choice(segments: list[WheelSegment]) -> WheelSegment:
    weights = [max(segment.weight, 0) for segment in segments]
    total = sum(weights)
    if total <= 0:
        return random.choice(segments)
    pick = random.uniform(0, total)
    cumulative = 0.0
    for segment, weight in zip(segments, weights):
        cumulative += weight
        if pick <= cumulative:
            return segment
    return segments[-1]


async def _find_existing_spin(
    session: AsyncSession, user_id: int, idempotency_key: str
) -> Spin | None:
    result = await session.execute(
        select(Spin).where(
            Spin.user_id == user_id,
            Spin.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def build_spin_response(session: AsyncSession, spin: Spin) -> dict:
    item: ContentItem | None = None
    if spin.content_item_id is not None:
        item = await session.get(ContentItem, spin.content_item_id)

    preview_media_id = None
    main_media_id = None
    if item is not None:
        preview_media_id = await get_first_media_asset_id(session, item.id, FileRole.PREVIEW)
        main_media_id = await get_first_media_asset_id(session, item.id, FileRole.MAIN)

    return {
        "spin_id": spin.id,
        "spin_type": spin.spin_type.value,
        "model_id": spin.model_id,
        "content_item_id": spin.content_item_id,
        "title": item.title if item else None,
        "description": item.description if item else None,
        "media_type": item.media_type.value if item else None,
        "rarity": item.rarity.value if item else None,
        "reward_gems": spin.reward_gems,
        "reward_spins": spin.reward_spins,
        "is_duplicate": spin.is_duplicate,
        "preview_media_id": preview_media_id,
        "main_media_id": main_media_id,
        "cost_spins": spin.cost_spins,
        "cost_gems": spin.cost_gems,
        "cost_stars": spin.cost_stars,
    }


async def grant_daily_free_spin(session: AsyncSession, user_id: int) -> dict:
    """Начислить 1 бесплатный спин колеса, если прошло не менее 24 часов."""
    user = await session.get(User, user_id)
    if not user:
        raise ValueError("User not found")

    now = datetime.now(timezone.utc)
    last = user.last_daily_wheel_spin_at
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if now - last < DAILY_FREE_SPIN_COOLDOWN:
            wallet = await get_wallet_by_user_id(session, user_id)
            return {"granted": False, "spins_balance": wallet.spins_balance}

    await adjust_balance(
        session=session,
        user_id=user_id,
        resource=TransactionResource.SPINS,
        amount=1,
        reason=TransactionReason.DAILY_FREE_SPIN,
        reference_id="daily_free",
    )
    user.last_daily_wheel_spin_at = now
    await session.commit()

    wallet = await get_wallet_by_user_id(session, user_id)
    return {"granted": True, "spins_balance": wallet.spins_balance}


async def daily_free_spin_status(session: AsyncSession, user_id: int) -> dict:
    user = await session.get(User, user_id)
    if not user:
        raise ValueError("User not found")
    wallet = await get_wallet_by_user_id(session, user_id)

    last = user.last_daily_wheel_spin_at
    ready = True
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        ready = datetime.now(timezone.utc) - last >= DAILY_FREE_SPIN_COOLDOWN

    return {
        "ready": ready,
        "last_daily_wheel_spin_at": last.isoformat() if last else None,
        "spins_balance": wallet.spins_balance,
    }


async def perform_wheel_spin(
    session: AsyncSession,
    user_id: int,
    model_id: int | None,
    idempotency_key: str,
) -> dict:
    existing = await _find_existing_spin(session, user_id, idempotency_key)
    if existing:
        return await build_spin_response(session, existing)

    wheel = await get_active_wheel_for_model(session, model_id)
    if not wheel:
        raise NoActiveWheel("No active wheel for this model")

    segments = await get_active_segments(session, wheel.id)
    if not segments:
        raise NoActiveWheel("No active segments")

    spin = Spin(
        user_id=user_id,
        model_id=model_id,
        wheel_id=wheel.id,
        spin_type=SpinType.BONUS,
        content_item_id=None,
        segment_id=None,
        cost_spins=1,
        idempotency_key=idempotency_key,
    )
    session.add(spin)
    await session.flush()

    try:
        await adjust_balance(
            session=session,
            user_id=user_id,
            resource=TransactionResource.SPINS,
            amount=-1,
            reason=TransactionReason.SPIN,
            reference_id=str(spin.id),
        )
    except InsufficientBalanceError as exc:
        raise InsufficientSpinBalance("No spins available") from exc

    segment = weighted_segment_choice(segments)
    spin.segment_id = segment.id
    spin.content_item_id = segment.content_item_id

    reward_gems = 0
    reward_spins = 0
    if segment.reward_type == RewardType.GEMS and segment.reward_gems > 0:
        await adjust_balance(
            session=session,
            user_id=user_id,
            resource=TransactionResource.GEMS,
            amount=segment.reward_gems,
            reason=TransactionReason.SPIN,
            reference_id=str(spin.id),
        )
        reward_gems = segment.reward_gems
    elif segment.reward_type == RewardType.SPINS and segment.reward_spins > 0:
        await adjust_balance(
            session=session,
            user_id=user_id,
            resource=TransactionResource.SPINS,
            amount=segment.reward_spins,
            reason=TransactionReason.SPIN,
            reference_id=str(spin.id),
        )
        reward_spins = segment.reward_spins

    spin.reward_gems = reward_gems
    spin.reward_spins = reward_spins

    session.add(
        SpinResult(
            spin_id=spin.id,
            content_item_id=spin.content_item_id,
            reward_gems=reward_gems,
            reward_spins=reward_spins,
            is_duplicate=False,
            rarity=None,
        )
    )
    await session.flush()

    return await build_spin_response(session, spin)


async def _is_duplicate(session: AsyncSession, user_id: int, content_item_id: int) -> bool:
    result = await session.execute(
        select(UserInventory.id)
        .where(
            UserInventory.user_id == user_id,
            UserInventory.content_item_id == content_item_id,
            UserInventory.source == InventorySource.SPIN,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _pick_media_content(session: AsyncSession, model: Model) -> ContentItem:
    weights = parse_rarity_weights(model.rarity_weights_json)

    result = await session.execute(
        select(ContentItem).where(
            ContentItem.model_id == model.id,
            ContentItem.status == ContentStatus.PUBLISHED,
        )
    )
    items = list(result.scalars().all())
    if not items:
        raise NoContentAvailable("No published content for this model")

    available_rarities = {item.rarity for item in items}
    candidate_rarities = [rarity for rarity in weights if rarity in available_rarities]
    if not candidate_rarities:
        return random.choice(items)

    chosen_rarity = random.choices(
        candidate_rarities,
        weights=[weights[rarity] for rarity in candidate_rarities],
        k=1,
    )[0]
    candidates = [item for item in items if item.rarity == chosen_rarity]
    return random.choice(candidates)


async def _finalize_media_spin(session: AsyncSession, spin: Spin, model: Model) -> dict:
    content = await _pick_media_content(session, model)

    is_duplicate = await _is_duplicate(session, spin.user_id, content.id)
    reward_gems = 0
    if is_duplicate:
        reward_gems = RARITY_DUPLICATE_REWARD_GEMS[content.rarity]
        await adjust_balance(
            session=session,
            user_id=spin.user_id,
            resource=TransactionResource.GEMS,
            amount=reward_gems,
            reason=TransactionReason.DUPLICATE_REFUND,
            reference_id=str(spin.id),
        )
    else:
        session.add(
            UserInventory(
                user_id=spin.user_id,
                content_item_id=content.id,
                source=InventorySource.SPIN,
                reference_id=spin.id,
            )
        )

    spin.content_item_id = content.id
    spin.reward_gems = reward_gems
    spin.is_duplicate = is_duplicate

    session.add(
        SpinResult(
            spin_id=spin.id,
            content_item_id=content.id,
            reward_gems=reward_gems,
            reward_spins=0,
            is_duplicate=is_duplicate,
            rarity=content.rarity,
        )
    )
    await session.flush()
    return await build_spin_response(session, spin)


async def perform_media_spin(
    session: AsyncSession,
    user_id: int,
    model_id: int,
    idempotency_key: str,
) -> dict:
    """Медиа-спин за GEMS."""
    existing = await _find_existing_spin(session, user_id, idempotency_key)
    if existing:
        return await build_spin_response(session, existing)

    model = await session.get(Model, model_id)
    if not model:
        raise ValueError("Model not found")
    if model.media_spin_price_gems <= 0:
        raise MediaSpinNotConfigured("Media spin price is not configured")

    spin = Spin(
        user_id=user_id,
        model_id=model_id,
        spin_type=SpinType.MEDIA,
        content_item_id=None,
        cost_gems=model.media_spin_price_gems,
        idempotency_key=idempotency_key,
    )
    session.add(spin)
    await session.flush()

    try:
        await adjust_balance(
            session=session,
            user_id=user_id,
            resource=TransactionResource.GEMS,
            amount=-model.media_spin_price_gems,
            reason=TransactionReason.SPIN,
            reference_id=str(spin.id),
        )
    except InsufficientBalanceError as exc:
        raise InsufficientGems("Insufficient gems") from exc

    return await _finalize_media_spin(session, spin, model)


async def complete_media_spin_with_stars(
    session: AsyncSession,
    user_id: int,
    model_id: int,
    idempotency_key: str,
    telegram_payment_charge_id: str | None = None,
) -> dict:
    """Медиа-спин за Telegram Stars (после подтверждения оплаты)."""
    existing = await _find_existing_spin(session, user_id, idempotency_key)
    if existing:
        return await build_spin_response(session, existing)

    model = await session.get(Model, model_id)
    if not model:
        raise ValueError("Model not found")
    if model.media_spin_price_stars <= 0:
        raise MediaSpinNotConfigured("Media spin price is not configured")

    spin = Spin(
        user_id=user_id,
        model_id=model_id,
        spin_type=SpinType.MEDIA,
        content_item_id=None,
        cost_stars=model.media_spin_price_stars,
        idempotency_key=idempotency_key,
    )
    session.add(spin)
    await session.flush()

    return await _finalize_media_spin(session, spin, model)


async def get_spin_by_id(session: AsyncSession, user_id: int, spin_id: int) -> dict:
    spin = await session.get(Spin, spin_id)
    if not spin or spin.user_id != user_id:
        raise ValueError("Spin not found")
    return await build_spin_response(session, spin)


async def get_spin_history(
    session: AsyncSession,
    user_id: int,
    spin_type: SpinType,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    result = await session.execute(
        select(Spin)
        .where(Spin.user_id == user_id, Spin.spin_type == spin_type)
        .order_by(Spin.id.desc())
        .limit(limit)
        .offset(offset)
    )
    spins = result.scalars().all()
    return [await build_spin_response(session, spin) for spin in spins]


async def send_media_to_chat(
    session: AsyncSession,
    model_id: int,
    user_id: int,
    media_asset_id: int | None,
) -> None:
    """Отправить медиа в чат пользовательского бота модели."""
    if media_asset_id is None:
        return
    model = await session.get(Model, model_id)
    if not model or not model.bot_token:
        return
    user = await session.get(User, user_id)
    if not user:
        return
    asset = await session.get(MediaAsset, media_asset_id)
    if not asset:
        return

    bot = create_telegram_bot(model.bot_token)
    try:
        if asset.file_type == MediaType.VIDEO:
            await bot.send_video(chat_id=user.telegram_id, video=asset.telegram_file_id)
        else:
            await bot.send_document(chat_id=user.telegram_id, document=asset.telegram_file_id)
    finally:
        await bot.session.close()
