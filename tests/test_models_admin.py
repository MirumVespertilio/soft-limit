import pytest
from sqlalchemy import select

from app.models.model import Model
from tests.test_auth import generate_init_data


async def _create_admin(client, telegram_id: int = 999999) -> str:
    admin_init = generate_init_data(telegram_id=telegram_id)
    admin_auth = await client.post("/api/v1/auth/telegram", json={"init_data": admin_init})
    return admin_auth.json()["access_token"]


async def _create_regular_user(client, telegram_id: int = 777001) -> str:
    user_init = generate_init_data(telegram_id=telegram_id)
    user_auth = await client.post("/api/v1/auth/telegram", json={"init_data": user_init})
    return user_auth.json()["access_token"]


async def test_admin_create_and_list_models(client, session):
    admin_token = await _create_admin(client, 999999)

    # 1. Создаем модель через админку
    create_resp = await client.post(
        "/api/v1/admin/models",
        json={
            "name": "Model Alice",
            "bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            "theme_json": '{"primary_color": "#ff007f", "accent": "#00ffcc"}',
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_resp.status_code == 200
    created_data = create_resp.json()
    model_id = created_data["id"]
    assert created_data["name"] == "Model Alice"
    assert created_data["bot_token"] == "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

    # 2. Получаем список моделей владельца
    list_resp = await client.get(
        "/api/v1/admin/models",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_resp.status_code == 200
    models = list_resp.json()["models"]
    assert any(m["id"] == model_id and m["name"] == "Model Alice" for m in models)


async def test_admin_get_and_update_model(client, session):
    admin_token = await _create_admin(client, 999999)

    # Создаем модель
    create_resp = await client.post(
        "/api/v1/admin/models",
        json={"name": "Model Bob", "bot_token": "token_bob"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    model_id = create_resp.json()["id"]

    # Читаем детали
    get_resp = await client.get(
        f"/api/v1/admin/models/{model_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Model Bob"

    # Обновляем имя и тему
    update_resp = await client.patch(
        f"/api/v1/admin/models/{model_id}",
        json={
            "name": "Model Bob Renamed",
            "theme_json": '{"theme": "dark_neon"}',
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert update_resp.status_code == 200
    updated_data = update_resp.json()
    assert updated_data["name"] == "Model Bob Renamed"
    assert updated_data["theme_json"] == '{"theme": "dark_neon"}'
    assert updated_data["bot_token"] == "token_bob"


async def test_regular_user_cannot_manage_models(client, session):
    user_token = await _create_regular_user(client, 777002)

    resp = await client.get(
        "/api/v1/admin/models",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403
    assert "Admin access required" in resp.json()["detail"]

    post_resp = await client.post(
        "/api/v1/admin/models",
        json={"name": "Hacker Model"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert post_resp.status_code == 403
