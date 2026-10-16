import pytest
from unittest.mock import AsyncMock, patch

from app.models.model import Model
from bot.manager import bot_manager, MultiBotManager
from bot.model_bot import get_model_user_dispatcher


def test_model_user_dispatcher_creation():
    dp = get_model_user_dispatcher(model_id=42, model_name="TestModel")
    assert dp is not None


@patch("bot.manager.create_model_bot")
async def test_bot_manager_registration(mock_create_bot):
    mock_bot = AsyncMock()
    mock_bot.session = AsyncMock()
    mock_create_bot.return_value = mock_bot

    manager = MultiBotManager()
    bot = manager.register_model_bot(model_id=10, model_name="Kira", bot_token="token_kira_123")
    assert bot == mock_bot
    assert manager.get_bot(10) == mock_bot
    assert manager.get_dispatcher(10) is not None

    await manager.close_all()


async def test_webhook_endpoint_not_found(client):
    # Запрос к боту, который не зарегистрирован в менеджере -> 404
    resp = await client.post("/api/v1/webhook/model/99999", json={})
    assert resp.status_code == 404
    assert "not active or not found" in resp.json()["detail"]


@patch("bot.manager.create_model_bot")
async def test_webhook_endpoint_feed_update(mock_create_bot, client):
    mock_bot = AsyncMock()
    mock_bot.session = AsyncMock()
    mock_create_bot.return_value = mock_bot

    # Регистрируем бота модели в глобальном менеджере
    bot_manager.register_model_bot(model_id=77, model_name="Luna", bot_token="token_luna")

    # Имитируем входящий вебхук от Telegram с update_id
    update_data = {
        "update_id": 10001,
        "message": {
            "message_id": 1,
            "date": 1700000000,
            "chat": {"id": 12345, "type": "private"},
            "from": {"id": 12345, "is_bot": False, "first_name": "TestUser"},
            "text": "/start",
        },
    }

    resp = await client.post("/api/v1/webhook/model/77", json=update_data)
    assert resp.status_code == 200

    await bot_manager.close_all()
