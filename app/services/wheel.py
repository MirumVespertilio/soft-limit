import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wheel import Wheel, WheelSegment
from app.models.content import ContentItem, ContentStatus


async def get_active_wheel(session: AsyncSession) -> Wheel | None:
    result = await session.execute(select(Wheel).where(Wheel.status == "active").order_by(Wheel.id))
    return result.scalars().first()


async def get_active_segments(session: AsyncSession, wheel_id: int) -> list[WheelSegment]:
    result = await session.execute(
        select(WheelSegment)
        .join(ContentItem, WheelSegment.content_item_id == ContentItem.id)
        .where(
            WheelSegment.wheel_id == wheel_id,
            WheelSegment.is_active.is_(True),
            ContentItem.status == ContentStatus.PUBLISHED,
        )
        .order_by(WheelSegment.position)
    )
    return list(result.scalars().all())


def weighted_random_choice(segments: list[WheelSegment]) -> WheelSegment:
    weights = [seg.weight for seg in segments]
    return random.choices(segments, weights=weights, k=1)[0]
