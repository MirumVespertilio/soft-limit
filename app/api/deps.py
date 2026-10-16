"""FastAPI-зависимости для аутентификации и авторизации.

Архитектура рассчитана на будущий multi-tenant SaaS:
- get_current_user  — возвращает объект User с подгруженной ролью
- require_admin     — проверяет роль через БД (а не хардкод telegram_id)
- get_current_telegram_id / get_current_user_id — оставлены для совместимости
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.security import decode_access_token
from app.models.user import User
from app.models.role import UserRole, RoleType

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    """DTO текущего авторизованного пользователя."""
    id: int
    telegram_id: int
    role: str  # "user" | "admin"
    model_id: int | None = None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    """Декодировать JWT и вернуть CurrentUser с актуальной ролью из БД."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token_data = decode_access_token(credentials.credentials)
    telegram_id: int = token_data["telegram_id"]
    model_id: int | None = token_data.get("model_id")

    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Достаём роль из БД (актуальная), fallback — "user"
    role_result = await session.execute(
        select(UserRole).where(UserRole.user_id == user.id)
    )
    role_row = role_result.scalar_one_or_none()
    role = role_row.role.value if role_row else RoleType.USER.value

    return CurrentUser(id=user.id, telegram_id=telegram_id, role=role, model_id=model_id)


async def require_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Разрешить доступ только пользователям с ролью admin."""
    if current_user.role != RoleType.ADMIN.value:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ── Обратная совместимость ─────────────────────────────────────────────────────

async def get_current_telegram_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> int:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token_data = decode_access_token(credentials.credentials)
    return token_data["telegram_id"]


async def get_current_user_id(
    telegram_id: int = Depends(get_current_telegram_id),
    session: AsyncSession = Depends(get_session),
) -> int:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user.id


async def get_current_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> int:
    """Обратная совместимость — проверяет роль через БД, возвращает telegram_id."""
    if current_user.role != RoleType.ADMIN.value:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user.telegram_id
