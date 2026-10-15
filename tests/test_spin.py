import pytest
from sqlalchemy import select

from app.models.user import User
from app.models.wallet import UserWallet
from app.models.spin import Spin, SpinType
from app.models.inventory import UserInventory
from app.models.content import ContentItem, ContentStatus, MediaType
from app.models.wheel import Wheel, WheelSegment
from app.models.welcome import WelcomeRewardItem
from tests.test_auth import generate_init_data


async def _create_user(client, telegram_id: int = 123456789) -> str:
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


async def test_welcome_spin(client, session):
    token = await _create_user(client, 111111)
    item_id = await _setup_wheel(session)

    session.add(WelcomeRewardItem(content_item_id=item_id))
    await session.commit()

    response = await client.post(
        "/api/v1/spins",
        json={"idempotency_key": "welcome-1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_welcome"] is True
    assert data["content_item_id"] == item_id

    wallet = await session.execute(select(UserWallet))
    assert wallet.scalars().first().spins_balance == 0


async def test_standard_spin(client, session):
    token = await _create_user(client, 222222)
    item_id = await _setup_wheel(session)

    session.add(WelcomeRewardItem(content_item_id=item_id))
    await session.commit()

    r1 = await client.post(
        "/api/v1/spins",
        json={"idempotency_key": "spin-1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200

    wallet = await session.execute(select(UserWallet))
    wallet.scalars().first().spins_balance = 5
    await session.commit()

    r2 = await client.post(
        "/api/v1/spins",
        json={"idempotency_key": "spin-2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["is_welcome"] is False

    wallet = await session.execute(select(UserWallet))
    assert wallet.scalars().first().spins_balance == 4


async def test_idempotent_spin(client, session):
    token = await _create_user(client, 333333)
    item_id = await _setup_wheel(session)

    session.add(WelcomeRewardItem(content_item_id=item_id))
    await session.commit()

    response1 = await client.post(
        "/api/v1/spins",
        json={"idempotency_key": "dup-key"},
        headers={"Authorization": f"Bearer {token}"},
    )
    response2 = await client.post(
        "/api/v1/spins",
        json={"idempotency_key": "dup-key"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response1.json() == response2.json()

    spins = await session.execute(select(Spin))
    assert len(spins.scalars().all()) == 1


async def test_insufficient_balance(client, session):
    token = await _create_user(client, 444444)
    item_id = await _setup_wheel(session)

    session.add(WelcomeRewardItem(content_item_id=item_id))
    await session.commit()

    await client.post(
        "/api/v1/spins",
        json={"idempotency_key": "s1"},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await client.post(
        "/api/v1/spins",
        json={"idempotency_key": "s2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "No spins" in response.json()["detail"]


async def test_parallel_spins(client, session):
    token = await _create_user(client, 555555)
    item_id = await _setup_wheel(session)

    session.add(WelcomeRewardItem(content_item_id=item_id))
    await session.commit()

    await client.post(
        "/api/v1/spins",
        json={"idempotency_key": "p0"},
        headers={"Authorization": f"Bearer {token}"},
    )

    wallet = await session.execute(select(UserWallet))
    wallet.scalars().first().spins_balance = 5
    await session.commit()

    success_count = 0
    for i in range(5):
        response = await client.post(
            "/api/v1/spins",
            json={"idempotency_key": f"par-{i}"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 200:
            success_count += 1

    assert success_count == 5

    spins = await session.execute(select(Spin))
    assert len(spins.scalars().all()) == 6
