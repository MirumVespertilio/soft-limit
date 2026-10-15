from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.user import User
from app.models.wallet import UserWallet, WalletTransaction, TransactionResource, TransactionReason
from app.security import verify_telegram_init_data, create_access_token, is_admin

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class AuthRequest(BaseModel):
    init_data: str


class AuthResponse(BaseModel):
    access_token: str
    is_new: bool
    is_admin: bool


@router.post("/telegram", response_model=AuthResponse)
async def telegram_auth(request: AuthRequest, session: AsyncSession = Depends(get_session)):
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

        wallet = UserWallet(user_id=user.id, test_stars_balance=0, spins_balance=1)
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

    await session.commit()

    return AuthResponse(
        access_token=create_access_token(telegram_id),
        is_new=is_new,
        is_admin=is_admin(telegram_id),
    )
