"""
pumpfun_scraper.py — Fetch callouts (replies) for the $SOLWATCH coin on pump.fun.

pump.fun has an undocumented frontend API. The replies endpoint has been
reverse-engineered by the community and works as of 2025, but may break
if pump.fun changes their backend.

If the real API fails, we fall back to the mock data defined at the bottom
so that the rest of the bot can still be tested without a live coin.

TODO: If the API endpoint breaks, inspect pump.fun's DevTools → Network tab
while viewing your coin's callouts page and look for a request like:
    GET https://frontend-api.pump.fun/replies/<MINT>?limit=1000&offset=0
Update PUMPFUN_REPLIES_URL_TEMPLATE below with whatever new endpoint you find.
"""
import logging
import time
from typing import Optional

import httpx

from config import settings
from db import upsert_callout

logger = logging.getLogger(__name__)

# ── Endpoint ───────────────────────────────────────────────────────────────────
# Updated to v3 API (frontend-api-v3.pump.fun) — confirmed working May 2026
PUMPFUN_API_V3_BASE = "https://frontend-api-v3.pump.fun"
PUMPFUN_CALLOUT_URL_TEMPLATE = (
    "{base}/callout/top/{mint}?limit=1000&sortBy=TIMESTAMP&sortOrder=DESC"
)

# Use mock data when True (for devnet testing or when API is unavailable)
USE_MOCK_DATA = False  # flip to True to test without a live coin


async def scrape_callouts() -> int:
    """
    Fetch all replies for the SOLWATCH coin from pump.fun and persist them.
    Returns the number of new callouts added.
    """
    if not settings.SOLWATCH_MINT_ADDRESS or settings.SOLWATCH_MINT_ADDRESS == "set_after_coin_deploy":
        logger.warning("SOLWATCH_MINT_ADDRESS not set — skipping callout scrape")
        return 0

    if USE_MOCK_DATA:
        return await _load_mock_callouts()

    return await _fetch_from_pumpfun_api()


async def _fetch_from_pumpfun_api() -> int:
    """
    Hit the pump.fun frontend API to pull all replies for our coin.

    Expected response shape (each item in the JSON array):
    {
        "user": "WalletPubkey...",
        "text": "i need a watch",
        "timestamp": 1234567890,   # unix seconds
        "mint": "TokenMintPubkey..."
    }

    pump.fun may use different field names — check the raw response and
    update the field extraction below if needed.
    """
    mint = settings.SOLWATCH_MINT_ADDRESS
    offset = 0
    page_size = 1000
    added = 0

    try:
        async with httpx.AsyncClient(
            timeout=settings.HTTP_TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Origin": "https://pump.fun",
                "Referer": f"https://pump.fun/coin/{mint}",
                "Accept": "application/json",
            },
        ) as client:

            url = PUMPFUN_CALLOUT_URL_TEMPLATE.format(
                base=PUMPFUN_API_V3_BASE,
                mint=mint,
            )
            logger.debug("Fetching callouts: %s", url)
            resp = await client.get(url)

            if resp.status_code == 404:
                logger.info("pump.fun returned 404 for mint %s (coin not live yet?)", mint)
                return 0

            if resp.status_code != 200:
                logger.warning("pump.fun callout API returned %d — will retry next cycle", resp.status_code)
                return added

            data = resp.json()
            callouts = data.get("callouts", [])

            for item in callouts:
                wallet = item.get("userId", "")
                text = item.get("thesis", "") or ""
                ts_raw = item.get("createdAt", 0)
                ts = int(ts_raw) // 1000 if ts_raw > 9_000_000_000_000 else int(ts_raw)
                if not wallet:
                    continue
                has_magic = settings.MAGIC_PHRASE in text.lower()
                upsert_callout(wallet, text, ts, has_magic)
                added += 1

        logger.info("Callout scrape complete: %d entries processed", added)
        return added

    except Exception as exc:
        logger.error("pump.fun API scrape failed: %s", exc)
        return 0


def _extract_reply_fields(item: dict) -> tuple[str, str, int]:
    """
    Extract (wallet, text, timestamp) from a pump.fun reply object.

    TODO: Update field names here if the API shape changes. Check the raw JSON
    from DevTools if you see empty wallets or texts in the logs.
    """
    # Try common field name variants seen in pump.fun responses
    wallet: str = (
        item.get("user")
        or item.get("wallet")
        or item.get("pubkey")
        or item.get("creator")
        or ""
    )
    text: str = (
        item.get("text")
        or item.get("message")
        or item.get("content")
        or item.get("body")
        or ""
    )
    ts_raw = (
        item.get("timestamp")
        or item.get("created_at")
        or item.get("time")
        or 0
    )

    # timestamp might be in milliseconds
    ts = int(ts_raw)
    if ts > 9_000_000_000_000:  # looks like milliseconds
        ts = ts // 1000
    if ts == 0:
        ts = int(time.time())

    return wallet, text, ts


# ── Mock data (for devnet testing) ────────────────────────────────────────────
#
# Populate MOCK_CALLOUTS with fake wallets that have the magic phrase.
# These must also be seeded into the holders table (handled by holder tracker).
# Replace the wallet addresses with devnet wallets you control for testing.
#
# TODO: Replace these with real devnet wallet addresses when running devnet tests.

MOCK_CALLOUTS = [
    {
        "user": "MOCK_WALLET_1_REPLACE_ME",
        "text": "hire me gm ser",
        "timestamp": int(time.time()) - 3600,
    },
    {
        "user": "MOCK_WALLET_2_REPLACE_ME",
        "text": "frens HIRE ME pls i need the bag",
        "timestamp": int(time.time()) - 1800,
    },
    {
        "user": "MOCK_WALLET_3_REPLACE_ME",
        "text": "hire me i will work hard",
        "timestamp": int(time.time()) - 900,
    },
    {
        "user": "MOCK_WALLET_4_NO_PHRASE",
        "text": "this coin is fire gm",
        "timestamp": int(time.time()) - 600,
    },
]


async def _load_mock_callouts() -> int:
    """Load MOCK_CALLOUTS into the database. Used for testing."""
    added = 0
    for item in MOCK_CALLOUTS:
        text = item["text"]
        has_magic = settings.MAGIC_PHRASE in text.lower()
        upsert_callout(item["user"], text, item["timestamp"], has_magic)
        added += 1
    logger.info("[MOCK] Loaded %d mock callouts", added)
    return added
