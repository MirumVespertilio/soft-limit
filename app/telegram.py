from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from app.config import settings


def create_telegram_bot() -> Bot:
    """Create a Bot API client using the optional local HTTP proxy."""
    proxy_url = settings.TELEGRAM_PROXY_URL.strip() or None
    session = AiohttpSession(proxy=proxy_url)
    return Bot(token=settings.TELEGRAM_BOT_TOKEN, session=session)
