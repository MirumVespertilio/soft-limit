import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

import jwt
from fastapi import HTTPException

from app.config import settings


def verify_telegram_init_data(init_data: str) -> dict:
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = params.pop("hash", "")
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", settings.TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid hash")

    try:
        auth_date = int(params.get("auth_date", 0))
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid auth_date")

    now = int(time.time())
    if auth_date > now + 300:
        raise HTTPException(status_code=401, detail="auth_date is in the future")
    if now - auth_date > 86400:
        raise HTTPException(status_code=401, detail="Init data expired")

    user_json = params.get("user", "{}")
    try:
        user_data = json.loads(user_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=401, detail="Invalid user data")

    if "id" not in user_data or not isinstance(user_data["id"], int) or user_data["id"] <= 0:
        raise HTTPException(status_code=401, detail="Invalid user id")

    user_data["auth_date"] = auth_date
    return user_data


def create_access_token(telegram_id: int, role: str = "user", model_id: int | None = None) -> str:
    """Создать JWT с telegram_id, ролью пользователя и опциональным model_id."""
    payload = {
        "sub": str(telegram_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    if model_id is not None:
        payload["model_id"] = model_id
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """Декодировать JWT и вернуть {"telegram_id": int, "role": str, "model_id": int | None}."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return {
            "telegram_id": int(payload["sub"]),
            "role": payload.get("role", "user"),
            "model_id": payload.get("model_id"),
        }
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")


def is_admin(telegram_id: int) -> bool:
    return telegram_id == settings.ADMIN_TELEGRAM_ID
