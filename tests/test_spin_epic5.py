import pytest
from sqlalchemy import select

from app.models.user import User
from app.models.wallet import UserWallet
from app.models.spin import Spin, SpinType
from app.models.inventory import UserInventory
from app.models.content import ContentItem, ContentStatus, MediaType, Rarity
from app.models.wheel import Wheel, WheelSegment, RewardType
from app.models.model import Model
from app.security import create_access_token
from tests.test_auth import generate_init_data


async def _create_user_with_model(client, session, telegram_id: int, **model_kwargs):
    init_data = generate_init_data(telegram_id=telegram_id)
    resp = await client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert resp.status_code == 200

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one()

    model = Model(name="Test Model", owner_user_id=user.id, **model_kwargs)
    session.add(model)
    await session.commit()

    token = create_access_token(user.telegram_id, role="user", model_id=model.id)
    return token, model, user


async def _set_balances(session, user_id: int, gems: int = 0, spins: int = 0):
    result = await session.execute(select(UserWallet).where(UserWallet.user_id == user_id))
    wallet = result.scalar_one()
    wallet.gems_balance = gems
    wallet.spins_balance = spins
    await session.commit()
    return wallet


async def _create_wheel(session, model_id: int, segments: list[dict]) -> int:
    wheel = Wheel(name="Test Wheel", model_id=model_id, status="active")
    session.add(wheel)
    await session.flush()
    for i, seg in enumerate(segments):
        session.add(WheelSegment(
            wheel_id=wheel.id,
            content_item_id=seg.get("content_item_id"),
            label=seg["label"],
            weight=seg.get("weight", 1),
            position=i,
            reward_type=seg.get("reward_type", RewardType.NONE),
            reward_gems=seg.get("reward_gems", 0),
            reward_spins=seg.get("reward_spins", 0),
        ))
    await session.commit()
    return wheel.id


async def _create_content(session, model_id: int, title: str, rarity: Rarity = Rarity.RARE) -> int:
    item = ContentItem(
        title=title,
        status=ContentStatus.PUBLISHED,
        media_type=MediaType.PHOTO,
        model_id=model_id,
        rarity=rarity,
    )
    session.add(item)
    await session.commit()
    return item.id


async def test_wheel_spin_rewards(client, session):
    token, model, user = await _create_user_with_model(client, session, 100001)
    await _create_wheel(session, model.id, [
        {"label": "+5 GEMS", "reward_type": RewardType.GEMS, "reward_gems": 5, "weight": 1},
    ])
    await _set_balances(session, user.id, gems=0, spins=1)

    response = await client.post(
        "/api/v1/spins/wheel",
        json={"idempotency_key": "wheel-1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["spin_type"] == "bonus"
    assert data["reward_gems"] == 5

    wallet = (await session.execute(
        select(UserWallet).where(UserWallet.user_id == user.id)
    )).scalar_one()
    assert wallet.spins_balance == 0
    assert wallet.gems_balance == 5


async def test_wheel_spin_insufficient(client, session):
    token, model, user = await _create_user_with_model(client, session, 100002)
    await _create_wheel(session, model.id, [{"label": "Prize", "weight": 1}])
    await _set_balances(session, user.id, gems=0, spins=0)

    response = await client.post(
        "/api/v1/spins/wheel",
        json={"idempotency_key": "wheel-insufficient"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "No spins" in response.json()["detail"]


async def test_wheel_spin_idempotent(client, session):
    token, model, user = await _create_user_with_model(client, session, 100003)
    await _create_wheel(session, model.id, [{"label": "Prize", "weight": 1}])
    await _set_balances(session, user.id, gems=0, spins=1)

    headers = {"Authorization": f"Bearer {token}"}
    r1 = await client.post("/api/v1/spins/wheel", json={"idempotency_key": "idem"}, headers=headers)
    r2 = await client.post("/api/v1/spins/wheel", json={"idempotency_key": "idem"}, headers=headers)

    assert r1.json()["spin_id"] == r2.json()["spin_id"]
    spins = (await session.execute(
        select(Spin).where(Spin.spin_type == SpinType.BONUS)
    )).scalars().all()
    assert len(spins) == 1

    wallet = (await session.execute(
        select(UserWallet).where(UserWallet.user_id == user.id)
    )).scalar_one()
    assert wallet.spins_balance == 0


async def test_daily_free_spin(client, session):
    token, model, user = await _create_user_with_model(client, session, 100004)
    await _set_balances(session, user.id, gems=0, spins=0)
    headers = {"Authorization": f"Bearer {token}"}

    r1 = await client.post("/api/v1/spins/daily-free", headers=headers)
    assert r1.status_code == 200
    assert r1.json()["granted"] is True

    r2 = await client.post("/api/v1/spins/daily-free", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["granted"] is False

    wallet = (await session.execute(
        select(UserWallet).where(UserWallet.user_id == user.id)
    )).scalar_one()
    assert wallet.spins_balance == 1


async def test_media_spin_gems(client, session):
    token, model, user = await _create_user_with_model(
        client, session, 100005, media_spin_price_gems=10, rarity_weights_json='{"rare": 100}'
    )
    await _create_content(session, model.id, "Media 1", Rarity.RARE)
    await _set_balances(session, user.id, gems=10, spins=0)

    response = await client.post(
        "/api/v1/spins/media",
        json={"idempotency_key": "media-1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["spin_type"] == "media"
    assert data["rarity"] == "rare"
    assert data["is_duplicate"] is False

    wallet = (await session.execute(
        select(UserWallet).where(UserWallet.user_id == user.id)
    )).scalar_one()
    assert wallet.gems_balance == 0

    inventory = (await session.execute(
        select(UserInventory).where(UserInventory.user_id == user.id)
    )).scalars().all()
    assert len(inventory) == 1


async def test_media_spin_duplicate_refund(client, session):
    token, model, user = await _create_user_with_model(
        client, session, 100006, media_spin_price_gems=10, rarity_weights_json='{"rare": 100}'
    )
    await _create_content(session, model.id, "Media Dup", Rarity.RARE)
    await _set_balances(session, user.id, gems=20, spins=0)
    headers = {"Authorization": f"Bearer {token}"}

    r1 = await client.post("/api/v1/spins/media", json={"idempotency_key": "d1"}, headers=headers)
    r2 = await client.post("/api/v1/spins/media", json={"idempotency_key": "d2"}, headers=headers)

    assert r1.json()["is_duplicate"] is False
    assert r2.json()["is_duplicate"] is True
    assert r2.json()["reward_gems"] == 1

    wallet = (await session.execute(
        select(UserWallet).where(UserWallet.user_id == user.id)
    )).scalar_one()
    assert wallet.gems_balance == 1

    inventory = (await session.execute(
        select(UserInventory).where(UserInventory.user_id == user.id)
    )).scalars().all()
    assert len(inventory) == 1


async def test_media_spin_insufficient_gems(client, session):
    token, model, user = await _create_user_with_model(
        client, session, 100007, media_spin_price_gems=10, rarity_weights_json='{"rare": 100}'
    )
    await _create_content(session, model.id, "Media 1", Rarity.RARE)
    await _set_balances(session, user.id, gems=5, spins=0)

    response = await client.post(
        "/api/v1/spins/media",
        json={"idempotency_key": "media-insufficient"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "gems" in response.json()["detail"].lower()


async def test_media_spin_stars(client, session):
    token, model, user = await _create_user_with_model(
        client, session, 100008, media_spin_price_gems=10, media_spin_price_stars=5,
        rarity_weights_json='{"rare": 100}'
    )
    await _create_content(session, model.id, "Media Stars", Rarity.RARE)
    await _set_balances(session, user.id, gems=0, spins=0)

    response = await client.post(
        "/api/v1/spins/media/complete",
        json={"model_id": model.id, "idempotency_key": "stars-1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["spin_type"] == "media"
    assert data["cost_stars"] == 5

    wallet = (await session.execute(
        select(UserWallet).where(UserWallet.user_id == user.id)
    )).scalar_one()
    assert wallet.gems_balance == 0


async def test_spin_history_split(client, session):
    token, model, user = await _create_user_with_model(
        client, session, 100009, media_spin_price_gems=10, rarity_weights_json='{"rare": 100}'
    )
    await _create_wheel(session, model.id, [{"label": "Prize", "weight": 1}])
    await _create_content(session, model.id, "Media 1", Rarity.RARE)
    await _set_balances(session, user.id, gems=10, spins=1)
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/v1/spins/wheel", json={"idempotency_key": "h-wheel"}, headers=headers)
    await client.post("/api/v1/spins/media", json={"idempotency_key": "h-media"}, headers=headers)

    wheel_history = await client.get("/api/v1/spins/history/wheel", headers=headers)
    media_history = await client.get("/api/v1/spins/history/media", headers=headers)

    assert wheel_history.status_code == 200
    assert media_history.status_code == 200
    assert len(wheel_history.json()["items"]) == 1
    assert wheel_history.json()["items"][0]["spin_type"] == "bonus"
    assert len(media_history.json()["items"]) == 1
    assert media_history.json()["items"][0]["spin_type"] == "media"


async def test_get_spin_by_id(client, session):
    token, model, user = await _create_user_with_model(
        client, session, 100010, media_spin_price_gems=10, rarity_weights_json='{"rare": 100}'
    )
    await _create_content(session, model.id, "Media 1", Rarity.RARE)
    await _set_balances(session, user.id, gems=10, spins=0)
    headers = {"Authorization": f"Bearer {token}"}

    spin = await client.post("/api/v1/spins/media", json={"idempotency_key": "by-id"}, headers=headers)
    spin_id = spin.json()["spin_id"]

    response = await client.get(f"/api/v1/spins/{spin_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["spin_id"] == spin_id

    missing = await client.get("/api/v1/spins/999999", headers=headers)
    assert missing.status_code == 404
