"""Менеджер мульти-бот инфраструктуры.

Управляет жизненным циклом и вебхуками ботов моделей:
- Загружает активные модели из базы данных
- Предоставляет единую точку входа для маршрутизации вебхуков
"""
import logging
from typing import Dict
from aiogram import Bot, Dispatcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model import Model
from bot.model_bot import get_model_user_dispatcher, create_model_bot

logger = logging.getLogger(__name__)


class MultiBotManager:
    def __init__(self):
        self._bots: Dict[int, Bot] = {}
        self._dispatchers: Dict[int, Dispatcher] = {}

    def register_model_bot(self, model_id: int, model_name: str, bot_token: str) -> Bot:
        """Зарегистрировать бота модели в памяти менеджера."""
        if model_id in self._bots:
            return self._bots[model_id]

        bot = create_model_bot(bot_token)
        dp = get_model_user_dispatcher(model_id=model_id, model_name=model_name)
        self._bots[model_id] = bot
        self._dispatchers[model_id] = dp
        logger.info(f"Registered user bot for model {model_name} (id={model_id})")
        return bot

    def get_bot(self, model_id: int) -> Bot | None:
        return self._bots.get(model_id)

    def get_dispatcher(self, model_id: int) -> Dispatcher | None:
        return self._dispatchers.get(model_id)

    async def load_all_model_bots(self, session: AsyncSession) -> int:
        """Загрузить все зарегистрированные модели с токенами из базы данных."""
        result = await session.execute(
            select(Model).where(Model.bot_token.isnot(None))
        )
        models = result.scalars().all()
        count = 0
        for m in models:
            if m.bot_token:
                self.register_model_bot(model_id=m.id, model_name=m.name, bot_token=m.bot_token)
                count += 1
        return count

    async def close_all(self):
        """Закрыть все клиентские сессии ботов."""
        for bot in self._bots.values():
            await bot.session.close()
        self._bots.clear()
        self._dispatchers.clear()


bot_manager = MultiBotManager()
