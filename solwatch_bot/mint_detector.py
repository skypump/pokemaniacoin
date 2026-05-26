from __future__ import annotations
"""
mint_detector.py — Auto-detect the SOLWATCH mint address.

Two methods:
1. Helius enhanced transactions — finds the most recent pump.fun coin
   created by the deploy wallet. Works even if coin already exists.
2. pumpdev.io WebSocket — real-time listener for new launches (backup).

Start the bot BEFORE or AFTER deploying — it will auto-detect either way.
"""
import asyncio
import json
import logging
import re
from pathlib import Path

import httpx

from config import settings

logger = logging.getLogger(__name__)

PUMPDEV_WS_URL = "wss://pumpdev.io/ws"


async def try_detect_mint() -> str | None:
    """
    Try both methods. Helius first (works for existing coins), then WebSocket.
    Returns mint address if found, None otherwise.
    """
    mint = await _detect_via_helius()
    if mint:
        return mint
    return await _detect_via_websocket()


_bot_start_time: int = int(__import__("time").time())


async def _detect_via_helius() -> str | None:
    """
    Watches for the first pump.fun BUY by deploy wallet after bot started.
    Dev always buys their own coin first — this catches it reliably.
    """
    wallet = settings.DEPLOY_WALLET_PUBLIC_KEY
    api_key = settings.HELIUS_RPC_URL.split("api-key=")[-1]
    url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={
                "api-key": api_key,
                "limit": 10,
            })
            if resp.status_code != 200:
                return None

            txs = resp.json()
            for tx in txs:
                if tx.get("source") != "PUMP_FUN":
                    continue
                # Only transactions after bot started
                if tx.get("timestamp", 0) < _bot_start_time:
                    continue
                # Look for any pump token received by deploy wallet (create or buy)
                for transfer in tx.get("tokenTransfers", []):
                    mint = transfer.get("mint", "")
                    to = transfer.get("toUserAccount", "")
                    if mint and to == wallet and mint.endswith("pump"):
                        logger.info("Mint detected via Helius (first buy): %s", mint)
                        return mint

    except Exception as exc:
        logger.debug("Helius mint detect error: %s", exc)

    return None


async def _detect_via_websocket() -> str | None:
    """Listen to pumpdev.io for new coin launches by our deploy wallet."""
    import websockets

    wallet = settings.DEPLOY_WALLET_PUBLIC_KEY
    logger.debug("Mint detect: listening on pumpdev.io for wallet %s", wallet[:8])

    try:
        async with websockets.connect(PUMPDEV_WS_URL, ping_interval=20, open_timeout=10) as ws:
            await ws.send(json.dumps({"method": "subscribeNewToken"}))

            async def listen():
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    if data.get("type") in ("connected", "subscribed", "error"):
                        continue
                    if data.get("txType") != "create":
                        continue
                    creator = data.get("traderPublicKey", "")
                    mint = data.get("mint", "")
                    if creator == wallet and mint:
                        logger.info("Coin detected via WebSocket: %s", mint)
                        return mint
                return None

            return await asyncio.wait_for(listen(), timeout=15)

    except asyncio.TimeoutError:
        return None
    except Exception as exc:
        logger.debug("WebSocket mint detect error: %s", exc)
        return None


def apply_mint(mint: str) -> None:
    """Set mint in memory and persist to .env."""
    settings.SOLWATCH_MINT_ADDRESS = mint
    _write_mint_to_env(mint)
    logger.info("Mint address set: %s", mint)


def _write_mint_to_env(mint: str) -> None:
    env_path = Path(".env")
    if not env_path.exists():
        logger.warning(".env not found — mint not persisted to disk")
        return
    content = env_path.read_text(encoding="utf-8")
    new_content = re.sub(
        r"^SOLWATCH_MINT_ADDRESS=.*$",
        f"SOLWATCH_MINT_ADDRESS={mint}",
        content,
        flags=re.MULTILINE,
    )
    env_path.write_text(new_content, encoding="utf-8")
    logger.info("Mint written to .env")


def mint_is_configured() -> bool:
    addr = settings.SOLWATCH_MINT_ADDRESS
    return bool(addr) and addr != "set_after_coin_deploy" and len(addr) > 20
