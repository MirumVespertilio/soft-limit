import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from app.config import settings


def generate_init_data(telegram_id: int = 123456789, username: str = "testuser") -> str:
    user = json.dumps({
        "id": telegram_id,
        "username": username,
        "first_name": "Test",
    })
    auth_date = int(time.time())
    params = {
        "user": user,
        "auth_date": str(auth_date),
        "query_id": "test_query",
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", settings.TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    params["hash"] = computed_hash
    return urlencode(params)


async def test_telegram_auth_success(client):
    init_data = generate_init_data()
    response = await client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["is_new"] is True


async def test_telegram_auth_invalid_hash(client):
    init_data = "user=%7B%22id%22%3A123%7D&auth_date=123&hash=invalid"
    response = await client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert response.status_code == 401


async def test_telegram_auth_expired(client):
    user = json.dumps({"id": 123, "username": "test"})
    params = {"user": user, "auth_date": str(int(time.time()) - 90000)}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", settings.TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    params["hash"] = computed_hash
    init_data = urlencode(params)
    response = await client.post("/api/v1/auth/telegram", json={"init_data": init_data})
    assert response.status_code == 401
