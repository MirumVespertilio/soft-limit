import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select

from app.models.wallet import (
    GemPackage,
    GemPurchase,
    UserWallet,
    TransactionResource,
    TransactionReason,
)
from app.models.purchases import SpinPackage, SpinPurchase
from tests.test_auth import generate_init_data


async def _seed_verified_payment(
    session, user_id: int, idempotency_key: str, amount: int, charge_id: str
):
    """Simulates the successful_payment webhook: creates a PAID Order + PaymentAttempt."""
    from app.models.order import Order
    from app.services.payments import build_invoice_payload, create_order, record_successful_payment

    result = await session.execute(
        select(Order)
        .where(Order.user_id == user_id, Order.amount == amount)
        .order_by(Order.id.desc())
        .limit(1)
    )
    order = result.scalar_one_or_none()
    if order is None:
        order = await create_order(
            session, user_id=user_id, product_type="test", product_id=None, amount=amount
        )
    payload = build_invoice_payload(order.id, idempotency_key)
    recorded = await record_successful_payment(session, payload, charge_id, amount)
    assert recorded is not None
    return order


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
    assert any(
        p["id"] == package_id and p["gems_amount"] == 100 and p["price_stars"] == 50
        for p in packages
    )


@patch("app.api.purchases.router.create_telegram_bot")
async def test_create_gem_invoice_link(mock_create_bot, client, session):
    mock_bot = AsyncMock()
    mock_bot.session = AsyncMock()
    mock_bot.create_invoice_link = AsyncMock(return_value="https://t.me/$invoice_link_test")
    mock_create_bot.return_value = mock_bot

    session.add(GemPackage(name="50 Gems", gems_amount=50, price_stars=25))
    await session.commit()
    pkg = (await session.execute(select(GemPackage))).scalars().first()

    token, model = await _create_user_with_model(client, session, 888002)
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
    assert data["idempotency_key"]


async def test_complete_gem_purchase_idempotent(client, session):
    session.add(GemPackage(name="200 Gems", gems_amount=200, price_stars=100))
    await session.commit()
    pkg = (await session.execute(select(GemPackage))).scalars().first()

    token, user_id = await _create_user(client, 888003)

    # Симулируем successful_payment webhook: платёж подтверждён до complete
    await _seed_verified_payment(session, user_id, "gem-purchase-key-1", 100, "tg_charge_12345")

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
    purchases = (
        (await session.execute(select(GemPurchase).where(GemPurchase.user_id == user_id)))
        .scalars()
        .all()
    )
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
    wallet = (
        (await session.execute(select(UserWallet).where(UserWallet.user_id == user_id)))
        .scalars()
        .first()
    )
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


# ==============================================================================
# Покупка спин-пакетов за Telegram Stars
# ==============================================================================


async def _create_user_with_model(
    client, session, telegram_id: int, bot_token: str | None = "500:test_bot_token"
):
    from app.models.user import User
    from app.models.model import Model
    from app.security import create_access_token

    init_data = generate_init_data(telegram_id=telegram_id)
    auth_resp = await client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert auth_resp.status_code == 200

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one()
    model = Model(name=f"M{telegram_id}", owner_user_id=user.id, bot_token=bot_token)
    session.add(model)
    await session.commit()
    token = create_access_token(telegram_id, role="user", model_id=model.id)
    return token, model


@patch("app.api.purchases.router.create_telegram_bot")
async def test_spin_packages_stars_flow(mock_create_bot, client, session):

    mock_bot = AsyncMock()
    mock_bot.session = AsyncMock()
    mock_bot.create_invoice_link = AsyncMock(return_value="https://t.me/$spin_invoice")
    mock_create_bot.return_value = mock_bot

    token, model = await _create_user_with_model(client, session, 888101)

    package = SpinPackage(
        name="Star Pack", spins_count=5, price_gems=40, price_stars=100, model_id=model.id
    )
    session.add(package)
    await session.commit()

    # 1. invoice-link через бота модели
    inv_resp = await client.post(
        "/api/v1/spin-purchases/invoice-link",
        json={"package_id": package.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert inv_resp.status_code == 200, inv_resp.text
    inv = inv_resp.json()
    assert inv["invoice_link"] == "https://t.me/$spin_invoice"
    assert inv["price_stars"] == 100
    assert inv["idempotency_key"]

    # Симулируем successful_payment webhook через бота модели
    me0 = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    await _seed_verified_payment(
        session, me0.json()["id"], inv["idempotency_key"], 100, "tg_spin_charge_1"
    )

    # 2. complete начисляет спины
    resp = await client.post(
        "/api/v1/spin-purchases/complete",
        json={
            "package_id": package.id,
            "idempotency_key": inv["idempotency_key"],
            "telegram_payment_charge_id": "tg_spin_charge_1",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["spins_added"] == 5
    assert data["price_stars"] == 100

    me = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["spins"] == 6  # 1 welcome + 5

    # 3. идемпотентность
    resp2 = await client.post(
        "/api/v1/spin-purchases/complete",
        json={"package_id": package.id, "idempotency_key": inv["idempotency_key"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["purchase_id"] == data["purchase_id"]
    me2 = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me2.json()["spins"] == 6

    purchase = (
        await session.execute(select(SpinPurchase).where(SpinPurchase.id == data["purchase_id"]))
    ).scalar_one()
    assert purchase.cost_stars == 100
    assert purchase.model_id == model.id


async def test_spin_invoice_requires_model_bot(client, session):
    pkg = SpinPackage(name="NoStars", spins_count=1, price_gems=0, price_stars=0)
    session.add(pkg)
    await session.commit()

    token = await _create_token_without_model(client, 888102)
    resp = await client.post(
        "/api/v1/spin-purchases/invoice-link",
        json={"package_id": pkg.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (400, 404)


async def _create_token_without_model(client, telegram_id: int) -> str:
    from app.security import create_access_token

    init_data = generate_init_data(telegram_id=telegram_id)
    resp = await client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    return create_access_token(telegram_id, role="user", model_id=None)


async def test_complete_requires_verified_payment(client, session):
    session.add(GemPackage(name="Chunks", gems_amount=10, price_stars=5))
    await session.commit()
    pkg = (await session.execute(select(GemPackage))).scalars().first()
    token, user_id = await _create_user(client, 888105)

    # Webhook ещё не пришёл — complete должен вернуть 409 для ретрая
    resp = await client.post(
        "/api/v1/gem-purchases/complete",
        json={"package_id": pkg.id, "idempotency_key": "unverified-key-1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409

    # После симуляции webhook покупка проходит
    await _seed_verified_payment(session, user_id, "unverified-key-1", 5, "tg_charge_manual_1")
    resp2 = await client.post(
        "/api/v1/gem-purchases/complete",
        json={"package_id": pkg.id, "idempotency_key": "unverified-key-1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["gems_added"] == 10


async def test_record_payment_mismatch_idempotency_and_garbage(session):
    from app.models.order import Order, PaymentAttempt
    from app.models.user import User
    from app.services.payments import (
        build_invoice_payload,
        create_order,
        parse_invoice_payload,
        record_successful_payment,
    )

    u = User(telegram_id=888106, username="pypass")
    session.add(u)
    await session.flush()
    order = await create_order(
        session, user_id=u.id, product_type="test", product_id=None, amount=10
    )
    payload = build_invoice_payload(order.id, "idem-mismatch")

    # Неверная сумма — платёж не подтверждается
    assert await record_successful_payment(session, payload, "chg_bad", 9) is None

    # Корректная сумма — Order становится PAID
    assert await record_successful_payment(session, payload, "chg_good", 10) is not None

    # Повторный webhook не дублирует PaymentAttempt
    assert await record_successful_payment(session, payload, "chg_good", 10) is not None
    attempts = (await session.execute(select(PaymentAttempt))).scalars().all()
    assert len(attempts) == 1
    order_db = await session.get(Order, order.id)
    assert order_db.status.value == "paid"

    # Мусорный payload отклоняется, разбор формата работает в обе стороны
    parsed = parse_invoice_payload(payload)
    assert parsed == (order.id, "idem-mismatch")
    assert await record_successful_payment(session, "garbage", "chg2", 10) is None
