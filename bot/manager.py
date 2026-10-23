"""Менеджер мульти-бот инфраструктуры.

Управляет жизненным циклом и вебхуками ботов моделей:
- Загружает активные модели из базы данных при старте приложения
- Регистрирует webhook каждого бота на POST /api/v1/webhook/model/{model_id}
- Позволяет (пере)регистрировать ботов в рантайме (например, при создании
  модели через админ-API)
"""

import logging
from typing import Dict

from aiogram import Bot, Dispatcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.model import Model
from bot.model_bot import get_model_user_dispatcher, create_model_bot

logger = logging.getLogger(__name__)


class MultiBotManager:
    def __init__(self):
        self._bots: Dict[int, Bot] = {}
        self._dispatchers: Dict[int, Dispatcher] = {}
        self._tokens: Dict[int, str] = {}

    def register_model_bot(self, model_id: int, model_name: str, bot_token: str) -> Bot:
        """Зарегистрировать бота модели в памяти менеджера (синхронно, без сети).

        Если бот уже зарегистрирован с тем же токеном — вернёт существующий.
        При смене токена старый клиент закрывается и создаётся заново
        (обновление webhook выполняет setup_model_bot / set_all_webhooks).
        """
        existing = self._bots.get(model_id)
        if existing and self._tokens.get(model_id) == bot_token:
            return existing
        if existing:
            logger.info(f"Re-registering bot for model id={model_id}: token changed")

        bot = create_model_bot(bot_token)
        dp = get_model_user_dispatcher(model_id=model_id, model_name=model_name)
        self._bots[model_id] = bot
        self._dispatchers[model_id] = dp
        self._tokens[model_id] = bot_token
        logger.info(f"Registered user bot for model {model_name} (id={model_id})")
        return bot

    def get_bot(self, model_id: int) -> Bot | None:
        return self._bots.get(model_id)

    def get_dispatcher(self, model_id: int) -> Dispatcher | None:
        return self._dispatchers.get(model_id)

    async def setup_model_bot(self, model_id: int, model_name: str, bot_token: str) -> Bot | None:
        """Зарегистрировать бота в рантайме и сразу выставить webhook.

        Ошибки регистрации webhook не прерывают работу (логируются),
        чтобы admin-API не падал из-за недоступности Telegram.
        """
        bot = self.register_model_bot(model_id, model_name, bot_token)
        await self.set_bot_webhook(model_id, bot)
        return bot

    def webhook_url(self, model_id: int) -> str | None:
        base = settings.APP_BASE_URL.rstrip("/")
        if not base:
            return None
        return f"{base}/api/v1/webhook/model/{model_id}"

    async def set_bot_webhook(self, model_id: int, bot: Bot) -> None:
        url = self.webhook_url(model_id)
        if not url:
            logger.warning("APP_BASE_URL is empty — webhook not set for model %s", model_id)
            return
        try:
            await bot.set_webhook(url)
            logger.info(f"Webhook set for model id={model_id}: {url}")
        except Exception:
            logger.exception(f"Failed to set webhook for model id={model_id}")

    async def load_all_model_bots(self, session: AsyncSession) -> int:
        """Загрузить все модели с токенами из базы и зарегистрировать ботов."""
        result = await session.execute(select(Model).where(Model.bot_token.isnot(None)))
        models = result.scalars().all()
        count = 0
        for m in models:
            if m.bot_token:
                self.register_model_bot(model_id=m.id, model_name=m.name, bot_token=m.bot_token)
                count += 1
        return count

    async def set_all_webhooks(self) -> None:
        """Выставить/обновить webhook для всех зарегистрированных ботов."""
        for model_id, bot in self._bots.items():
            if self._tokens.get(model_id) != "":
                await self.set_bot_webhook(model_id, bot)

    async def close_all(self):
        """Закрыть все клиентские сессии ботов."""
        for bot in self._bots.values():
            await bot.session.close()
        self._bots.clear()
        self._dispatchers.clear()
        self._tokens.clear()


bot_manager = MultiBotManager()
