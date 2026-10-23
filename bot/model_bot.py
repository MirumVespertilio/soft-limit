"""Диспетчер и хэндлеры пользовательского бота конкретной модели.

Каждая модель имеет свой собственный токен и бота:
- Пользователь открывает Mini-App с передачей model_id
- Вся переписка и медиа отправляются строго в чат этой конкретной модели
- Хендлеры платежей Telegram Stars: pre_checkout_query и successful_payment
"""

import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PreCheckoutQuery,
    WebAppInfo,
)

from app.config import settings
from app.telegram import create_telegram_bot

logger = logging.getLogger(__name__)


async def _record_payment(session_factory, successful_payment, message: Message) -> None:
    from app.services.payments import record_successful_payment

    sp = successful_payment
    async with session_factory() as session:
        try:
            order = await record_successful_payment(
                session,
                sp.invoice_payload,
                sp.telegram_payment_charge_id,
                sp.total_amount,
                sp.currency,
            )
            if order is None:
                logger.error(
                    "successful_payment with malformed/unknown payload from chat %s: %r",
                    message.chat.id,
                    sp.invoice_payload,
                )
        except Exception:
            logger.exception("Failed to record successful payment (order flow)")


def get_model_user_dispatcher(model_id: int, model_name: str) -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def cmd_user_start(message: Message):
        user_webapp_url = f"{settings.APP_BASE_URL}/static/user/index.html?model_id={model_id}"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"✨ Открыть {model_name}",
                        web_app=WebAppInfo(url=user_webapp_url),
                    )
                ]
            ]
        )
        await message.answer(
            f"Привет! Ты в официальном боте модели {model_name}. 💖\n"
            f"Крути колесо, получай эксклюзивные медиа и собирай коллекцию!",
            reply_markup=keyboard,
        )

    @dp.pre_checkout_query()
    async def handle_pre_checkout(pre_checkout_query: PreCheckoutQuery):
        """Telegram требует подтверждения pre_checkout — иначе платёж не пройдёт."""
        try:
            await pre_checkout_query.answer(ok=True)
        except Exception:
            logger.exception("Failed to answer pre_checkout_query for model %s", model_id)

    @dp.message(F.successful_payment)
    async def handle_successful_payment(message: Message):
        from app.db import async_session

        try:
            await _record_payment(async_session, message.successful_payment, message)
        except Exception:
            logger.exception("Failed to process successful_payment for model %s", model_id)

    return dp


def create_model_bot(bot_token: str) -> Bot:
    """Создать экземпляр бота модели по её персональному токену."""
    return create_telegram_bot(token=bot_token)
