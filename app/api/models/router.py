"""Публичный API для получения параметров модели (включая тему оформления Mini-App)."""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.model import Model

router = APIRouter(prefix="/api/v1/models", tags=["models"])


class ModelThemeResponse(BaseModel):
    model_id: int
    name: str
    theme: dict


@router.get("/{model_id}/theme", response_model=ModelThemeResponse)
async def get_model_theme(
    model_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Получить тему оформления Mini-App конкретной модели для кастомизации UI."""
    model = await session.get(Model, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    theme_data = {}
    if model.theme_json:
        try:
            theme_data = json.loads(model.theme_json)
        except Exception:
            theme_data = {}

    return ModelThemeResponse(
        model_id=model.id,
        name=model.name,
        theme=theme_data,
    )
