"""Вебхук-эндпоинт для мульти-бот архитектуры.

Принимает входящие события от Telegram Bot API по персональному URL модели:
POST /api/v1/webhook/model/{model_id}
"""

import logging
from fastapi import APIRouter, HTTPException, Request, Response
from aiogram.types import Update

from bot.manager import bot_manager

router = APIRouter(prefix="/api/v1/webhook", tags=["webhook"])
logger = logging.getLogger(__name__)


@router.post("/model/{model_id}")
async def model_bot_webhook(model_id: int, request: Request):
    bot = bot_manager.get_bot(model_id)
    dp = bot_manager.get_dispatcher(model_id)

    if not bot or not dp:
        raise HTTPException(status_code=404, detail="Model bot not active or not found")

    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot=bot, update=update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Error handling update for model {model_id}: {e}")
        return Response(status_code=200)
