"""
price_oracle.py — SOL/USD price with a simple in-memory cache.
Uses CoinGecko free API (no key needed, ~50 req/min limit).
"""
import asyncio
import logging
import time

import httpx

from config import settings

logger = logging.getLogger(__name__)

_cached_price: float = 0.0
_cache_timestamp: float = 0.0
_price_lock = asyncio.Lock()


async def get_sol_price_usd() -> float:
    """
    Return SOL/USD price. Cached for SOL_PRICE_CACHE_SECONDS.
    Falls back to last known price if the request fails.
    """
    global _cached_price, _cache_timestamp

    async with _price_lock:
        age = time.monotonic() - _cache_timestamp
        if age < settings.SOL_PRICE_CACHE_SECONDS and _cached_price > 0:
            return _cached_price

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(settings.COINGECKO_PRICE_URL)
                resp.raise_for_status()
                data = resp.json()
                price = float(data["solana"]["usd"])

            _cached_price = price
            _cache_timestamp = time.monotonic()
            logger.debug("SOL price refreshed: $%.2f", price)
            return price

        except Exception as exc:
            logger.warning("Failed to fetch SOL price: %s — using last known $%.2f", exc, _cached_price)
            if _cached_price > 0:
                return _cached_price
            # No cached value at all — raise so callers know we can't proceed
            raise RuntimeError("SOL price unavailable and no cache") from exc


def lamports_to_usd(lamports: int, sol_price: float) -> float:
    """Convert lamports to USD given a SOL price."""
    return (lamports / 1_000_000_000) * sol_price


def usd_to_lamports(usd: float, sol_price: float) -> int:
    """Convert a USD amount to lamports. Returns integer (truncated)."""
    sol_amount = usd / sol_price
    return int(sol_amount * 1_000_000_000)
