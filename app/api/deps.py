from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.security import decode_access_token, is_admin
from app.config import settings
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_telegram_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> int:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return decode_access_token(credentials.credentials)


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
    telegram_id: int = Depends(get_current_telegram_id),
) -> int:
    if not is_admin(telegram_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    return telegram_id
