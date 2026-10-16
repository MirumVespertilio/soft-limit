"""Admin-бот платформы Soft Limit (для владельцев моделей и администратора).

Через него открывается админ-панель:
- Управление своими моделями
- Привязка ботов и тем оформления
- Аналитика и статистика выручки
"""
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.config import settings
from app.telegram import create_telegram_bot


def get_admin_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def cmd_admin_start(message: Message):
        admin_webapp_url = f"{settings.APP_BASE_URL}/static/admin/index.html"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text="🛠 Открыть панель управления",
                    web_app=WebAppInfo(url=admin_webapp_url),
                )
            ]]
        )
        await message.answer(
            f"👋 Добро пожаловать в панель управления платформой!\n\n"
            f"Здесь вы можете подключать ботов своих моделей, настраивать колесо фортуны и просматривать аналитику.",
            reply_markup=keyboard,
        )

    return dp


async def run_admin_bot():
    bot = create_telegram_bot()
    dp = get_admin_dispatcher()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run_admin_bot())
