"""
main.py — Entry point. Runs all bot loops and the FastAPI server concurrently.

Usage:
    python main.py

Kill with Ctrl+C.

Manual overrides (run in a second terminal while bot is running):
    python -c "from draw import force_draw_cli; force_draw_cli()"
    python -c "import asyncio; from pumpfun_collector import print_vault_info; asyncio.run(print_vault_info())"
"""
import asyncio
import logging
import sys
import time

import uvicorn

from api import app
from config import settings
from db import (
    get_conn,
    get_shift_started_at,
    init_db,
    state_get,
    state_set,
    start_new_shift,
    try_verify_callout_bonus,
    get_wallets_with_magic_phrase,
)
from draw import check_and_execute_shift
from holder_tracker import update_holders
from mint_detector import apply_mint, mint_is_configured, try_detect_mint
from price_oracle import get_sol_price_usd, lamports_to_usd
from pumpfun_collector import collect_creator_fees
from pumpfun_scraper import scrape_callouts
from reward_tracker import poll_deploy_balance
from score_calculator import compute_scores

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("solwatch_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("solwatch")


# ── Per-component loops ────────────────────────────────────────────────────────

async def mint_detector_loop() -> None:
    if mint_is_configured():
        logger.info("Mint already configured: %s", settings.SOLWATCH_MINT_ADDRESS)
        return
    logger.info("Waiting for coin deploy — watching %s on pump.fun...", settings.DEPLOY_WALLET_PUBLIC_KEY)
    while not mint_is_configured():
        mint = await try_detect_mint()
        if mint:
            apply_mint(mint)
            logger.info("=" * 60)
            logger.info("COIN DETECTED — bot is now fully active")
            logger.info("Mint: %s", mint)
            logger.info("=" * 60)
            return
        await asyncio.sleep(10)


async def _wait_for_mint() -> None:
    while not mint_is_configured():
        await asyncio.sleep(2)


async def callout_loop() -> None:
    """Scrape pump.fun callouts and verify callout bonuses for eligible wallets."""
    await _wait_for_mint()
    while True:
        t0 = time.monotonic()
        try:
            count = await scrape_callouts()
            logger.debug("callout_loop: %d entries", count)

            # Check if any newly scraped wallets qualify for the permanent callout bonus
            wallets_with_phrase = get_wallets_with_magic_phrase()
            for wallet in wallets_with_phrase:
                newly_verified = try_verify_callout_bonus(wallet, settings.MIN_HOLDER_BALANCE)
                if newly_verified:
                    logger.info(
                        "CALLOUT BONUS GRANTED: %s — permanent +1 multiplier (score doubled)",
                        wallet[:8] + "...",
                    )
        except Exception as exc:
            logger.error("callout_loop error: %s", exc)
        elapsed = time.monotonic() - t0
        await asyncio.sleep(max(0, settings.CALLOUT_POLL_INTERVAL - elapsed))


async def holder_loop() -> None:
    """Update holder balances + detect buys/sells every HOLDER_POLL_INTERVAL seconds."""
    await _wait_for_mint()
    await asyncio.sleep(10)
    while True:
        t0 = time.monotonic()
        try:
            await update_holders()
        except Exception as exc:
            logger.error("holder_loop error: %s", exc)
        elapsed = time.monotonic() - t0
        await asyncio.sleep(max(0, settings.HOLDER_POLL_INTERVAL - elapsed))


async def score_loop() -> None:
    """Recompute scores every SCORE_CALC_INTERVAL seconds."""
    await _wait_for_mint()
    await asyncio.sleep(15)
    while True:
        t0 = time.monotonic()
        try:
            compute_scores()
        except Exception as exc:
            logger.error("score_loop error: %s", exc)
        elapsed = time.monotonic() - t0
        await asyncio.sleep(max(0, settings.SCORE_CALC_INTERVAL - elapsed))


async def reward_loop() -> None:
    """Log deploy wallet balance every REWARD_POLL_INTERVAL seconds."""
    await asyncio.sleep(20)
    while True:
        t0 = time.monotonic()
        try:
            await poll_deploy_balance()
        except Exception as exc:
            logger.error("reward_loop error: %s", exc)
        elapsed = time.monotonic() - t0
        await asyncio.sleep(max(0, settings.REWARD_POLL_INTERVAL - elapsed))


async def shift_loop() -> None:
    """Check shift end every DRAW_CHECK_INTERVAL seconds."""
    await _wait_for_mint()
    await asyncio.sleep(25)
    while True:
        t0 = time.monotonic()
        try:
            await check_and_execute_shift()
        except Exception as exc:
            logger.error("shift_loop error: %s", exc)
        elapsed = time.monotonic() - t0
        await asyncio.sleep(max(0, settings.DRAW_CHECK_INTERVAL - elapsed))


async def collect_loop() -> None:
    """
    Auto-collect pump.fun creator fees every 5 seconds.
    SHIFT_VAULT_FRACTION (80%) of collected fees go into the shift vault.
    The vault is distributed pro-rata to all workers at shift end.
    """
    await _wait_for_mint()
    await asyncio.sleep(5)
    while True:
        try:
            collected_lamports = await collect_creator_fees()
            if collected_lamports > 0:
                from db import add_to_shift_vault, get_shift_vault_lamports
                vault_cut = int(collected_lamports * settings.SHIFT_VAULT_FRACTION)
                new_vault = add_to_shift_vault(vault_cut)

                try:
                    sol_price = await get_sol_price_usd()
                    logger.info(
                        "Vault +%.6f SOL ($%.2f) | total: %.6f SOL ($%.2f)",
                        vault_cut / 1e9,
                        lamports_to_usd(vault_cut, sol_price),
                        new_vault / 1e9,
                        lamports_to_usd(new_vault, sol_price),
                    )
                except Exception:
                    logger.info("Vault +%d lamports | total: %d lamports", vault_cut, new_vault)
        except Exception as exc:
            logger.error("collect_loop error: %s", exc)
        await asyncio.sleep(0.7)


# ── FastAPI server ─────────────────────────────────────────────────────────────

async def run_api_server() -> None:
    config = uvicorn.Config(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()


# ── Main ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    logger.info("=" * 60)
    logger.info("$BANKER Bot starting up")
    logger.info("Mint: %s", settings.SOLWATCH_MINT_ADDRESS or "NOT SET — auto-detecting")
    logger.info("Deploy wallet: %s", settings.DEPLOY_WALLET_PUBLIC_KEY)
    logger.info(
        "Shift: %ds | Vault fraction: %.0f%% | Magic phrase: '%s' | Min balance: %d",
        settings.SHIFT_INTERVAL_SECONDS,
        settings.SHIFT_VAULT_FRACTION * 100,
        settings.MAGIC_PHRASE,
        settings.MIN_HOLDER_BALANCE,
    )
    logger.info("Click weight: %d | API: http://localhost:%d", settings.CLICK_WEIGHT, settings.API_PORT)
    logger.info("=" * 60)

    init_db()

    # Initialise shift timer if not already in DB
    if not state_get("shift_started_at", ""):
        start_new_shift()

    # Validate required config
    missing = []
    if not settings.DEPLOY_WALLET_PRIVATE_KEY:
        missing.append("DEPLOY_WALLET_PRIVATE_KEY")
    if not settings.DEPLOY_WALLET_PUBLIC_KEY:
        missing.append("DEPLOY_WALLET_PUBLIC_KEY")
    if not settings.HELIUS_RPC_URL:
        missing.append("HELIUS_RPC_URL")
    if missing:
        logger.error("Missing required env vars: %s", ", ".join(missing))
        sys.exit(1)

    logger.info("API server starting on http://localhost:%d", settings.API_PORT)

    await asyncio.gather(
        run_api_server(),
        mint_detector_loop(),
        callout_loop(),
        holder_loop(),
        score_loop(),
        collect_loop(),
        reward_loop(),
        shift_loop(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C). Goodbye.")
