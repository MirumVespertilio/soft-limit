from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db import get_session
from app.models.user import User
from app.models.wallet import UserWallet
from app.models.role import UserRole, RoleType

router = APIRouter(prefix="/api/v1", tags=["users"])


class MeResponse(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    gems: int
    spins: int
    is_admin: bool


@router.get("/me", response_model=MeResponse)
async def get_me(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(User, UserWallet).join(UserWallet).where(User.id == user_id)
    )
    row = result.one_or_none()
    if not row:
        raise ValueError("User not found")

    user, wallet = row

    role_result = await session.execute(select(UserRole).where(UserRole.user_id == user.id))
    role_row = role_result.scalar_one_or_none()
    user_is_admin = (role_row.role == RoleType.ADMIN) if role_row else False

    return MeResponse(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        gems=wallet.gems_balance,
        spins=wallet.spins_balance,
        is_admin=user_is_admin,
    )
