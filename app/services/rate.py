"""Currency rate helpers: Telegram Stars -> TON -> USD conversion.

Stars -> TON uses a fixed config rate (Telegram withdrawal pricing is stable
enough for accounting). TON -> USD is fetched live from CoinGecko and cached in
memory; on any failure the fallback constant is used.
"""

import asyncio
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_last_refresh: float = 0.0
_cached_rate: float = 0.0
_lock = asyncio.Lock()


def stars_to_ton(stars: int) -> float:
    return stars * settings.STARS_TO_TON_RATE


async def get_ton_usd_rate(session: httpx.AsyncClient | None = None) -> float:
    """Return current TON -> USD rate; cached for TON_USD_RATE_TTL seconds."""
    now = time.monotonic()
    if _cached_rate > 0 and now - _last_refresh < settings.TON_USD_RATE_TTL:
        return _cached_rate

    async with _lock:
        now = time.monotonic()
        if _cached_rate > 0 and now - _last_refresh < settings.TON_USD_RATE_TTL:
            return _cached_rate

        owned = session is None
        try:
            if owned:
                session = httpx.AsyncClient(timeout=settings.TON_USD_API_TIMEOUT)
            response = await session.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "the-open-network", "vs_currencies": "usd"},
            )
            response.raise_for_status()
            data = response.json()
            rate = float(data["the-open-network"]["usd"])
            if rate > 0:
                globals()["_cached_rate"] = rate
                globals()["_last_refresh"] = now
                return rate
        except Exception as exc:
            logger.warning(
                "TON/USD rate fetch failed, using fallback %.2f: %s", settings.TON_USD_FALLBACK, exc
            )
        finally:
            if owned and session is not None:
                await session.aclose()
        return settings.TON_USD_FALLBACK


def fallback_ton_usd_rate() -> float:
    return settings.TON_USD_FALLBACK


async def stars_to_usd(stars: int, session: httpx.AsyncClient | None = None) -> float:
    return stars_to_ton(stars) * await get_ton_usd_rate(session)


def reset_rate_cache() -> None:
    globals()["_cached_rate"] = 0.0
    globals()["_last_refresh"] = 0.0
