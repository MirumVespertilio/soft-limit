import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select

from app.models.wallet import GemPackage, GemPurchase, UserWallet, TransactionResource, TransactionReason
from app.models.purchases import SpinPackage, SpinPurchase
from tests.test_auth import generate_init_data


async def _create_user(client, telegram_id: int = 888888) -> tuple[str, int]:
    init_data = generate_init_data(telegram_id=telegram_id)
    response = await client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    token = response.json()["access_token"]
    me_resp = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    return token, me_resp.json()["id"]


async def test_list_and_create_gem_package(client, session):
    admin_init = generate_init_data(telegram_id=999999)
    admin_auth = await client.post("/api/v1/auth/telegram", json={"init_data": admin_init})
    admin_token = admin_auth.json()["access_token"]

    create_resp = await client.post(
        "/api/v1/admin/gem-packages",
        json={"name": "100 Gems Pack", "gems_amount": 100, "price_stars": 50, "position": 1},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_resp.status_code == 200
    package_id = create_resp.json()["id"]

    token, user_id = await _create_user(client, 888001)
    list_resp = await client.get(
        "/api/v1/gem-packages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    packages = list_resp.json()["packages"]
    assert any(p["id"] == package_id and p["gems_amount"] == 100 and p["price_stars"] == 50 for p in packages)


@patch("app.api.purchases.router.create_telegram_bot")
async def test_create_gem_invoice_link(mock_create_bot, client, session):
    mock_bot = AsyncMock()
    mock_bot.session = AsyncMock()
    mock_bot.create_invoice_link = AsyncMock(return_value="https://t.me/$invoice_link_test")
    mock_create_bot.return_value = mock_bot

    session.add(GemPackage(name="50 Gems", gems_amount=50, price_stars=25))
    await session.commit()
    pkg = (await session.execute(select(GemPackage))).scalars().first()

    token, user_id = await _create_user(client, 888002)
    resp = await client.post(
        "/api/v1/gem-purchases/invoice-link",
        json={"package_id": pkg.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["invoice_link"] == "https://t.me/$invoice_link_test"
    assert data["gems_amount"] == 50
    assert data["price_stars"] == 25


async def test_complete_gem_purchase_idempotent(client, session):
    session.add(GemPackage(name="200 Gems", gems_amount=200, price_stars=100))
    await session.commit()
    pkg = (await session.execute(select(GemPackage))).scalars().first()

    token, user_id = await _create_user(client, 888003)

    # Баланс до покупки
    me_before = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me_before.json()["gems"] == 0

    # Завершаем покупку (первый вызов)
    resp1 = await client.post(
        "/api/v1/gem-purchases/complete",
        json={
            "package_id": pkg.id,
            "idempotency_key": "gem-purchase-key-1",
            "telegram_payment_charge_id": "tg_charge_12345",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["gems_added"] == 200

    # Баланс после покупки
    me_after = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me_after.json()["gems"] == 200

    # Повторный вызов с тем же idempotency_key (должен быть идемпотентным и не начислять повторно)
    resp2 = await client.post(
        "/api/v1/gem-purchases/complete",
        json={
            "package_id": pkg.id,
            "idempotency_key": "gem-purchase-key-1",
            "telegram_payment_charge_id": "tg_charge_12345",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["purchase_id"] == resp1.json()["purchase_id"]

    me_final = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me_final.json()["gems"] == 200

    # Проверяем запись в gem_purchases
    purchases = (await session.execute(select(GemPurchase).where(GemPurchase.user_id == user_id))).scalars().all()
    assert len(purchases) == 1
    assert purchases[0].gems_added == 200
    assert purchases[0].telegram_payment_charge_id == "tg_charge_12345"


async def test_purchase_spins_with_gems(client, session):
    session.add(SpinPackage(name="5 Spins", spins_count=5, price_gems=50))
    await session.commit()
    pkg = (await session.execute(select(SpinPackage))).scalars().first()

    token, user_id = await _create_user(client, 888004)

    # Попытка купить спины без гемов -> 400
    fail_resp = await client.post(
        "/api/v1/spin-purchases",
        json={"package_id": pkg.id, "idempotency_key": "spin-buy-fail"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert fail_resp.status_code == 400
    assert "Insufficient gems" in fail_resp.json()["detail"]

    # Пополняем гемы
    wallet = (await session.execute(select(UserWallet).where(UserWallet.user_id == user_id))).scalars().first()
    wallet.gems_balance = 100
    await session.commit()

    # Покупка спинов
    buy_resp = await client.post(
        "/api/v1/spin-purchases",
        json={"package_id": pkg.id, "idempotency_key": "spin-buy-ok"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert buy_resp.status_code == 200
    data = buy_resp.json()
    assert data["spins_added"] == 5
    assert data["price_gems"] == 50

    # Проверяем списание гемов и зачисление спинов
    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["gems"] == 50
    # Изначально был 1 welcome spin + 5 купленных = 6
    assert me.json()["spins"] == 6
