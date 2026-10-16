from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession

from app.config import settings


def create_telegram_bot(token: str | None = None) -> Bot:
    """Create a Bot API client using the optional local HTTP proxy and token."""
    bot_token = token or settings.TELEGRAM_BOT_TOKEN
    proxy_url = settings.TELEGRAM_PROXY_URL.strip() or None
    session = AiohttpSession(proxy=proxy_url)
    return Bot(token=bot_token, session=session)
