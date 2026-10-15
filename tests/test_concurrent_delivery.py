import os
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token_for_tests")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_tests")
os.environ.setdefault("ADMIN_TELEGRAM_ID", "999999")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select

from app.models.spin import Spin
from app.models.inventory import UserInventory
from app.models.content import ContentItem, ContentStatus, MediaType, ContentItemMedia, MediaAsset, FileRole
from app.models.wheel import Wheel, WheelSegment
from app.models.welcome import WelcomeRewardItem
from tests.test_auth import generate_init_data


async def _create_user(client, telegram_id: int) -> str:
    init_data = generate_init_data(telegram_id=telegram_id)
    response = await client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    return response.json()["access_token"]


async def _setup_wheel(session):
    item1 = ContentItem(title="Prize 1", status=ContentStatus.PUBLISHED, media_type=MediaType.PHOTO)
    item2 = ContentItem(title="Prize 2", status=ContentStatus.PUBLISHED, media_type=MediaType.PHOTO)
    session.add_all([item1, item2])
    await session.flush()

    wheel = Wheel(name="Test Wheel", status="active")
    session.add(wheel)
    await session.flush()

    session.add_all([
        WheelSegment(wheel_id=wheel.id, content_item_id=item1.id, label="Prize 1", weight=1, position=0),
        WheelSegment(wheel_id=wheel.id, content_item_id=item2.id, label="Prize 2", weight=1, position=1),
    ])
    await session.commit()
    return item1.id


@patch("aiogram.Bot")
async def test_concurrent_delivery_single_send(mock_bot_cls, concurrent_client, concurrent_engine):
    client = concurrent_client
    mock_bot = AsyncMock()
    mock_bot.session = AsyncMock()
    mock_bot_cls.return_value = mock_bot

    token = await _create_user(client, 888888)

    async_session = async_sessionmaker(concurrent_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        item_id = await _setup_wheel(session)
        session.add(WelcomeRewardItem(content_item_id=item_id))
        await session.flush()

        asset = MediaAsset(
            file_type=MediaType.PHOTO,
            telegram_file_id="test_file_id",
            telegram_file_unique_id="test_unique_id",
            mime_type="image/jpeg",
            file_size=1024,
        )
        session.add(asset)
        await session.flush()

        session.add(ContentItemMedia(content_item_id=item_id, media_asset_id=asset.id, role=FileRole.ORIGINAL))
        await session.commit()

    await client.post("/api/v1/spins", json={"idempotency_key": "d1"}, headers={"Authorization": f"Bearer {token}"})

    async with async_session() as session:
        inv = await session.execute(select(UserInventory))
        inv_id = inv.scalars().first().id

    async def do_deliver():
        return await client.post(
            f"/api/v1/inventory/{inv_id}/deliver",
            headers={"Authorization": f"Bearer {token}"},
        )

    responses = await asyncio.gather(*[do_deliver() for _ in range(3)], return_exceptions=True)

    success_count = sum(1 for r in responses if hasattr(r, 'status_code') and r.status_code == 200)
    assert success_count == 3

    assert mock_bot.send_document.call_count == 1
