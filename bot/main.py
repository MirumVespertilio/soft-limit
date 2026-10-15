import asyncio

from aiogram import Bot, Dispatcher

from app.config import settings


async def main() -> None:
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
