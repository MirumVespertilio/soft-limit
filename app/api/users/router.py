from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db import get_session
from app.models.user import User
from app.models.wallet import UserWallet

router = APIRouter(prefix="/api/v1", tags=["users"])


class MeResponse(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    test_stars: int
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
    from app.security import is_admin

    return MeResponse(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        test_stars=wallet.test_stars_balance,
        spins=wallet.spins_balance,
        is_admin=is_admin(user.telegram_id),
    )
