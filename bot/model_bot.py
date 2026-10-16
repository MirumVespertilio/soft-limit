"""Диспетчер и хэндлеры пользовательского бота конкретной модели.

Каждая модель имеет свой собственный токен и бота:
- Пользователь открывает Mini-App с передачей model_id
- Вся переписка и медиа отправляются строго в чат этой конкретной модели
"""
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.config import settings
from app.telegram import create_telegram_bot


def get_model_user_dispatcher(model_id: int, model_name: str) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def cmd_user_start(message: Message):
        user_webapp_url = f"{settings.APP_BASE_URL}/static/user/index.html?model_id={model_id}"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text=f"✨ Открыть {model_name}",
                    web_app=WebAppInfo(url=user_webapp_url),
                )
            ]]
        )
        await message.answer(
            f"Привет! Ты в официальном боте модели {model_name}. 💖\n"
            f"Крути колесо, получай эксклюзивные медиа и собирай коллекцию!",
            reply_markup=keyboard,
        )

    return dp


def create_model_bot(bot_token: str) -> Bot:
    """Создать экземпляр бота модели по её персональному токену."""
    return create_telegram_bot(token=bot_token)
