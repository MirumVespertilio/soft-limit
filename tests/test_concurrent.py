import os
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token_for_tests")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_tests")
os.environ.setdefault("ADMIN_TELEGRAM_ID", "999999")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.models.user import User
from app.models.wallet import UserWallet
from app.models.spin import Spin
from app.models.inventory import UserInventory
from app.models.content import ContentItem, ContentStatus, MediaType, ContentItemMedia, MediaAsset, FileRole
from app.models.wheel import Wheel, WheelSegment
from app.models.welcome import WelcomeRewardItem
from app.models.purchases import SpinPackage
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


async def _make_engine():
    engine = create_async_engine("sqlite+aiosqlite:///./test.db", echo=False)
    async with engine.begin() as conn:
        from app.db import Base
        await conn.run_sync(Base.metadata.create_all)
    return engine


async def _do_spin_request(engine, token, idem_key):
    from app.main import app
    from app.db import get_session as orig_get_session

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with async_session() as s:
            yield s

    app.dependency_overrides[orig_get_session] = override_get_session
    try:
        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            return await c.post(
                "/api/v1/spins",
                json={"idempotency_key": idem_key},
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.pop(orig_get_session, None)


async def _do_purchase_request(engine, token, package_id, idem_key):
    from app.main import app
    from app.db import get_session as orig_get_session

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_session():
        async with async_session() as s:
            yield s

    app.dependency_overrides[orig_get_session] = override_get_session
    try:
        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            return await c.post(
                "/api/v1/spin-purchases",
                json={"package_id": package_id, "idempotency_key": idem_key},
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.pop(orig_get_session, None)


@pytest.mark.asyncio
async def test_real_concurrent_spins(client, session):
    token = await _create_user(client, 555555)
    item_id = await _setup_wheel(session)
    session.add(WelcomeRewardItem(content_item_id=item_id))
    await session.commit()

    await client.post("/api/v1/spins", json={"idempotency_key": "p0"}, headers={"Authorization": f"Bearer {token}"})

    wallet = await session.execute(select(UserWallet))
    wallet.scalars().first().spins_balance = 5
    await session.commit()

    engine = await _make_engine()

    responses = await asyncio.gather(*[
        _do_spin_request(engine, token, f"conc-{i}")
        for i in range(5)
    ], return_exceptions=True)

    success_count = sum(1 for r in responses if hasattr(r, 'status_code') and r.status_code == 200)
    assert success_count == 5

    spins = await session.execute(select(Spin))
    assert len(spins.scalars().all()) == 6


@pytest.mark.asyncio
async def test_real_concurrent_purchases(client, session):
    token = await _create_user(client, 666666)
    item_id = await _setup_wheel(session)
    session.add(WelcomeRewardItem(content_item_id=item_id))
    session.add(SpinPackage(name="Pack", spins_count=10, price_test_stars=5))
    await session.commit()

    wallet = await session.execute(select(UserWallet))
    wallet.scalars().first().test_stars_balance = 5
    await session.commit()

    pkg = await session.execute(select(SpinPackage))
    package_id = pkg.scalars().first().id

    engine = await _make_engine()

    responses = await asyncio.gather(*[
        _do_purchase_request(engine, token, package_id, f"cp-{i}")
        for i in range(3)
    ], return_exceptions=True)

    success_count = sum(1 for r in responses if hasattr(r, 'status_code') and r.status_code == 200)
    assert success_count == 1


@patch("aiogram.Bot")
async def test_delivery_bot_called_once(mock_bot_cls, client, session):
    mock_bot = AsyncMock()
    mock_bot.session = AsyncMock()
    mock_bot_cls.return_value = mock_bot

    token = await _create_user(client, 777777)
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

    inv = await session.execute(select(UserInventory))
    inv_id = inv.scalars().first().id

    await client.post(f"/api/v1/inventory/{inv_id}/deliver", headers={"Authorization": f"Bearer {token}"})
    await client.post(f"/api/v1/inventory/{inv_id}/deliver", headers={"Authorization": f"Bearer {token}"})

    assert mock_bot.send_document.call_count == 1
