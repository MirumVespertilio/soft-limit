from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.security import decode_access_token, is_admin
from app.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> int:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    telegram_id = decode_access_token(credentials.credentials)
    return telegram_id


async def get_current_admin(
    user_id: int = Depends(get_current_user_id),
) -> int:
    if not is_admin(user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id
