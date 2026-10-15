import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import WebAppInfo
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode

from app.config import settings


async def main() -> None:
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def cmd_start(message):
        webapp_url = f"{settings.APP_BASE_URL}/static/index.html"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Открыть", web_app=WebAppInfo(url=webapp_url))
        ]])
        await message.answer("Добро пожаловать!", reply_markup=keyboard)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
