import pytest
from app.models.model import Model
from tests.test_auth import generate_init_data


async def test_auth_with_model_id_and_me(client, session):
    # Создаем модель в БД
    model = Model(name="Eva", owner_user_id=1, theme_json='{"accent": "#ff0055"}')
    session.add(model)
    await session.commit()
    await session.refresh(model)

    # Авторизуемся с указанием model_id
    init_data = generate_init_data(telegram_id=654321)
    auth_resp = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": init_data, "model_id": model.id},
    )
    assert auth_resp.status_code == 200
    auth_data = auth_resp.json()
    assert auth_data["model_id"] == model.id
    token = auth_data["access_token"]

    # Проверяем /api/v1/auth/me — токен сохранил контекст model_id
    me_resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["model_id"] == model.id


async def test_get_model_theme(client, session):
    theme_json = '{"background": "#121212", "primary": "#bb86fc"}'
    model = Model(name="CyberGirl", owner_user_id=1, theme_json=theme_json)
    session.add(model)
    await session.commit()
    await session.refresh(model)

    theme_resp = await client.get(f"/api/v1/models/{model.id}/theme")
    assert theme_resp.status_code == 200
    data = theme_resp.json()
    assert data["model_id"] == model.id
    assert data["name"] == "CyberGirl"
    assert data["theme"]["background"] == "#121212"
    assert data["theme"]["primary"] == "#bb86fc"

    # Несуществующая модель
    notFound_resp = await client.get("/api/v1/models/999999/theme")
    assert notFound_resp.status_code == 404
