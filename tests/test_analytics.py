import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update

from app.models.user import User
from app.models.model import Model
from app.models.wallet import UserWallet, GemPurchase
from app.models.spin import Spin, SpinType
from app.models.spin_result import SpinResult, Rarity
from app.models.purchases import SpinPackage, SpinPurchase
from app.security import create_access_token
from tests.test_auth import generate_init_data


async def _create_user(client, session, telegram_id: int, model: Model | None = None) -> str:
    init_data = generate_init_data(telegram_id=telegram_id)
    resp = await client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert resp.status_code == 200
    if model is not None:
        return create_access_token(telegram_id, role="user", model_id=model.id)
    return resp.json()["access_token"]


async def _create_model(session, owner_user_id: int, name: str = "Model") -> Model:
    model = Model(name=name, owner_user_id=owner_user_id)
    session.add(model)
    await session.commit()
    return model


async def _add_spin(
    session,
    user_id: int,
    model_id: int,
    spin_type: SpinType,
    cost_gems: int = 0,
    cost_stars: int = 0,
    created_at: datetime | None = None,
) -> Spin:
    now = datetime.now(timezone.utc)
    spin = Spin(
        user_id=user_id,
        model_id=model_id,
        spin_type=spin_type,
        cost_gems=cost_gems,
        cost_stars=cost_stars,
        idempotency_key=f"analytics-{user_id}-{now.timestamp()}-{now.microsecond}",
    )
    session.add(spin)
    await session.flush()
    if created_at is not None:
        spin.created_at = created_at
    await session.commit()
    return spin


async def _get_admin_token(client) -> str:
    init_data = generate_init_data(telegram_id=999999)
    resp = await client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def fixed_rate(monkeypatch):
    """Deterministic TON->USD rate: 1 TON = 2 USD (Stars = 0.0047 TON)."""

    async def fake_rate(session=None):
        return 2.0

    monkeypatch.setattr("app.services.analytics.get_ton_usd_rate", fake_rate)
    return 2.0


async def test_stats_aggregates(client, session, fixed_rate):
    admin_token = await _get_admin_token(client)
    admin = (await session.execute(select(User).where(User.telegram_id == 999999))).scalar_one()
    model = await _create_model(session, admin.id)

    u1 = await _create_user(client, session, 300001, model)
    await _create_user(client, session, 300002)

    # Media spin paid with GEMS
    await _add_spin(session, admin.id, model.id, SpinType.MEDIA, cost_gems=50)
    # Media spin paid with Stars
    await _add_spin(session, admin.id, model.id, SpinType.MEDIA, cost_stars=100)
    # Wheel spin (free-of-charge in GEMS/Stars)
    await _add_spin(session, admin.id, model.id, SpinType.BONUS)

    # Spin package purchase: 10 GEMS + 40 Stars
    package = SpinPackage(name="Pack", spins_count=3, price_gems=10, price_stars=40)
    session.add(package)
    await session.commit()
    session.add(
        SpinPurchase(
            user_id=admin.id,
            package_id=package.id,
            price_gems=10,
            cost_stars=40,
            spins_added=3,
            idempotency_key="sp-1",
        )
    )
    # GEMS package purchase: 150 Stars
    session.add(
        GemPurchase(
            user_id=admin.id, package_id=1, gems_added=100, price_stars=150, idempotency_key="gp-1"
        )
    )
    await session.commit()

    response = await client.get(
        "/api/v1/admin/stats?period=all",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    t = data["totals"]

    assert t["spins_by_type"]["media"] == 2
    assert t["spins_by_type"]["bonus"] == 1
    assert t["revenue_gems_spent"] == 60  # 50 + 10
    assert t["revenue_stars"] == 290  # 100 + 40 + 150
    assert t["revenue_by_type"]["media_spins_gems"] == 50
    assert t["revenue_by_type"]["spin_packages_gems"] == 10
    assert t["revenue_by_type"]["spin_packages_stars"] == 40
    assert t["revenue_by_type"]["gem_packages_stars"] == 150
    assert t["purchases_total"] == 2
    assert t["buyers"] == 1
    # users: admin + 2 = 3; buyers 1/3
    assert t["users_total"] == 3
    assert t["conversion_rate"] == round(1 / 3, 4)

    # USD: 290 * 0.0047 * 2
    expected_usd = round(290 * 0.0047 * 2.0, 3)
    assert t["revenue_usd"] == expected_usd

    # Daily series covers 30 days with no zeros missing
    assert len(data["daily"]) == 30
    assert data["daily"][-1]["spins"] == 3
    assert data["daily"][-1]["revenue_gems_spent"] == 60
    assert data["daily"][-1]["revenue_stars"] == 290

    # per-model: media spins attributed to the model; the spin purchase is global (no model)
    pm = {m["model_id"]: m for m in data["per_model"]}
    assert model.id in pm
    assert pm[model.id]["spins_by_type"]["media"] == 2
    assert pm[model.id]["revenue_gems_spent"] == 50
    assert pm[model.id]["spin_purchases"] == 0
    expected_model_usd = round(100 * 0.0047 * 2.0, 3)
    assert pm[model.id]["revenue_usd"] == expected_model_usd


async def test_stats_period_filter(client, session, fixed_rate):
    admin_token = await _get_admin_token(client)
    admin = (await session.execute(select(User).where(User.telegram_id == 999999))).scalar_one()
    model = await _create_model(session, admin.id)

    now = datetime.now(timezone.utc)
    await _add_spin(
        session,
        admin.id,
        model.id,
        SpinType.MEDIA,
        cost_gems=30,
        created_at=now - timedelta(days=10),
    )
    await _add_spin(
        session,
        admin.id,
        model.id,
        SpinType.MEDIA,
        cost_gems=5,
        created_at=now - timedelta(hours=2),
    )

    resp_all = await client.get(
        "/api/v1/admin/stats?period=all",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_all.json()["totals"]["revenue_gems_spent"] == 35

    resp_month = await client.get(
        "/api/v1/admin/stats?period=month",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_month.json()["totals"]["revenue_gems_spent"] == 35

    resp_week = await client.get(
        "/api/v1/admin/stats?period=week",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_week.json()["totals"]["revenue_gems_spent"] == 5

    resp_day = await client.get(
        "/api/v1/admin/stats?period=day",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_day.json()["totals"]["revenue_gems_spent"] == 5


async def test_stats_results_and_duplicates(client, session, fixed_rate):
    admin_token = await _get_admin_token(client)
    admin = (await session.execute(select(User).where(User.telegram_id == 999999))).scalar_one()
    model = await _create_model(session, admin.id)

    spin1 = await _add_spin(session, admin.id, model.id, SpinType.MEDIA, cost_gems=10)
    spin2 = await _add_spin(session, admin.id, model.id, SpinType.MEDIA, cost_gems=10)
    spin3 = await _add_spin(session, admin.id, model.id, SpinType.MEDIA, cost_gems=10)
    session.add_all(
        [
            SpinResult(spin_id=spin1.id, rarity=Rarity.RARE, is_duplicate=True, reward_gems=1),
            SpinResult(spin_id=spin2.id, rarity=Rarity.MYTHIC, is_duplicate=False),
            SpinResult(spin_id=spin3.id, rarity=Rarity.RARE, is_duplicate=True, reward_gems=1),
        ]
    )
    await session.commit()

    response = await client.get(
        "/api/v1/admin/stats?period=all",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    t = response.json()["totals"]
    assert t["results_total"] == 3
    assert t["duplicates"] == 2
    assert t["duplicate_refund_gems"] == 2
    assert t["results_by_rarity"]["rare"] == 2
    assert t["results_by_rarity"]["mythic"] == 1


async def test_stats_model_filter(client, session, fixed_rate):
    admin_token = await _get_admin_token(client)
    admin = (await session.execute(select(User).where(User.telegram_id == 999999))).scalar_one()
    model_a = await _create_model(session, admin.id, "A")
    model_b = await _create_model(session, admin.id, "B")

    await _add_spin(session, admin.id, model_a.id, SpinType.MEDIA, cost_gems=10)
    await _add_spin(session, admin.id, model_b.id, SpinType.MEDIA, cost_gems=20)

    resp_a = await client.get(
        f"/api/v1/admin/stats?period=all&model_id={model_a.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    t = resp_a.json()["totals"]
    assert t["revenue_gems_spent"] == 10
    assert t["spins_by_type"]["media"] == 1

    # per_model always shows both models with data
    resp_all = await client.get(
        "/api/v1/admin/stats?period=all",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    pm_ids = {m["model_id"] for m in resp_all.json()["per_model"]}
    assert {model_a.id, model_b.id} <= pm_ids


async def test_spin_packages_model_scope(client, session, fixed_rate):
    admin_token = await _get_admin_token(client)
    admin = (await session.execute(select(User).where(User.telegram_id == 999999))).scalar_one()
    model_a = await _create_model(session, admin.id, "A")
    model_b = await _create_model(session, admin.id, "B")

    session.add_all(
        [
            SpinPackage(name="Global", spins_count=1, price_gems=5, model_id=None, is_active=True),
            SpinPackage(
                name="ModelA extra",
                spins_count=2,
                price_gems=8,
                model_id=model_a.id,
                is_active=True,
            ),
        ]
    )
    await session.commit()

    token_a = await _create_user(client, session, 310001, model_a)
    token_b = await _create_user(client, session, 310002, model_b)

    resp_a = await client.get(
        "/api/v1/spin-packages", headers={"Authorization": f"Bearer {token_a}"}
    )
    resp_b = await client.get(
        "/api/v1/spin-packages", headers={"Authorization": f"Bearer {token_b}"}
    )

    names_a = [p["name"] for p in resp_a.json()["packages"]]
    names_b = [p["name"] for p in resp_b.json()["packages"]]
    assert "Global" in names_a and "ModelA extra" in names_a
    assert "Global" in names_b and "ModelA extra" not in names_b

    # Purchase of model-scoped package stores model_id
    uid_a = (await session.execute(select(User).where(User.telegram_id == 310001))).scalar_one()
    wallet = (
        await session.execute(select(UserWallet).where(UserWallet.user_id == uid_a.id))
    ).scalar_one()
    wallet.gems_balance = 100
    await session.commit()

    pkg_a = [p for p in resp_a.json()["packages"] if p["name"] == "ModelA extra"][0]
    resp_buy = await client.post(
        "/api/v1/spin-purchases",
        json={"package_id": pkg_a["id"], "idempotency_key": "buy-1"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_buy.status_code == 200
    purchase = (await session.execute(select(SpinPurchase))).scalar_one()
    assert purchase.model_id == model_a.id

    # User of another model cannot buy model-scoped package
    uid_b = (await session.execute(select(User).where(User.telegram_id == 310002))).scalar_one()
    wallet_b = (
        await session.execute(select(UserWallet).where(UserWallet.user_id == uid_b.id))
    ).scalar_one()
    wallet_b.gems_balance = 100
    await session.commit()

    resp_denied = await client.post(
        "/api/v1/spin-purchases",
        json={"package_id": pkg_a["id"], "idempotency_key": "buy-2"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_denied.status_code == 404


async def test_stats_requires_admin(client, session, fixed_rate):
    token = await _create_user(client, session, 320001)
    response = await client.get(
        "/api/v1/admin/stats?period=all",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
