"""Эндпоинты аутентификации через Telegram Mini App.

POST /api/v1/auth/telegram — принимает init_data от Telegram,
  создаёт пользователя при первом входе, выдаёт JWT с ролью.
GET  /api/v1/auth/me       — возвращает профиль текущего пользователя.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.user import User
from app.models.role import UserRole, RoleType
from app.models.wallet import UserWallet, WalletTransaction, TransactionResource, TransactionReason
from app.security import verify_telegram_init_data, create_access_token
from app.api.deps import get_current_user, CurrentUser
from app.config import settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class AuthRequest(BaseModel):
    init_data: str
    model_id: int | None = None


class AuthResponse(BaseModel):
    access_token: str
    is_new: bool
    role: str
    model_id: int | None = None


class MeResponse(BaseModel):
    id: int
    telegram_id: int
    role: str
    model_id: int | None = None


@router.post("/telegram", response_model=AuthResponse)
async def telegram_auth(request: AuthRequest, session: AsyncSession = Depends(get_session)):
    """Авторизация по Telegram init_data. Создаёт пользователя и кошелёк при первом входе."""
    user_data = verify_telegram_init_data(request.init_data)
    telegram_id = int(user_data["id"])

    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    is_new = user is None
    if is_new:
        user = User(
            telegram_id=telegram_id,
            username=user_data.get("username"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
        )
        session.add(user)
        await session.flush()

        # Создаём кошелёк с приветственным спином
        wallet = UserWallet(user_id=user.id, gems_balance=0, spins_balance=1)
        session.add(wallet)
        await session.flush()

        tx = WalletTransaction(
            wallet_id=wallet.id,
            resource=TransactionResource.SPINS,
            amount=1,
            reason=TransactionReason.WELCOME_SPIN,
        )
        session.add(tx)
        user.welcome_spin_granted_at = datetime.now(timezone.utc)

        # Новые пользователи получают роль по умолчанию;
        # пользователь с ADMIN_TELEGRAM_ID автоматически становится admin
        default_role = RoleType.ADMIN if telegram_id == settings.ADMIN_TELEGRAM_ID else RoleType.USER
        user_role = UserRole(user_id=user.id, role=default_role)
        session.add(user_role)

    # Получаем актуальную роль из БД (для существующих пользователей)
    role_result = await session.execute(
        select(UserRole).where(UserRole.user_id == user.id)
    )
    role_row = role_result.scalar_one_or_none()
    role = role_row.role.value if role_row else RoleType.USER.value

    await session.commit()

    return AuthResponse(
        access_token=create_access_token(telegram_id, role=role, model_id=request.model_id),
        is_new=is_new,
        role=role,
        model_id=request.model_id,
    )


@router.get("/me", response_model=MeResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)):
    """Вернуть профиль текущего пользователя с его ролью и контекстом модели."""
    return MeResponse(
        id=current_user.id,
        telegram_id=current_user.telegram_id,
        role=current_user.role,
        model_id=current_user.model_id,
    )
