"""
holder_tracker.py — Poll token balances for ALL token holders and detect BUY / SELL events.

Timer rules:
  - First buy: timer starts NOW
  - Additional buys (topping up): timer keeps running from the original start
  - Any sell: disqualified instantly, timer wiped
  - Re-buy after sell: timer restarts fresh from NOW
"""
import asyncio
import logging
import time

from config import settings
from db import (
    ensure_holder_exists,
    get_eligible_wallets,
    get_holder,
    update_holder_balance_no_change,
    update_holder_buy,
    update_holder_sell,
)
from solana_client import get_all_token_holders

logger = logging.getLogger(__name__)


async def update_holders() -> None:
    """
    Fetch ALL wallets holding the mint, then update BUY/SELL status for each.
    """
    if not settings.SOLWATCH_MINT_ADDRESS:
        logger.debug("Mint not configured yet — skipping holder update")
        return

    try:
        all_holders = await get_all_token_holders(settings.SOLWATCH_MINT_ADDRESS)
    except Exception as exc:
        logger.error("Failed to fetch token holders: %s", exc)
        return

    if not all_holders:
        logger.debug("No token holders found")
        return

    logger.info("Polling balances for %d token holders...", len(all_holders))
    errors = 0

    for wallet, new_balance in all_holders.items():
        try:
            await _process_wallet_with_balance(wallet, new_balance)
        except Exception as exc:
            errors += 1
            logger.error("Balance update failed for %s: %s", wallet[:8] + "...", exc)

    # Wallets that were eligible but no longer appear on-chain sold everything
    for wallet in get_eligible_wallets():
        if wallet not in all_holders:
            try:
                logger.info("SELL (full exit): %s | no longer on-chain — DISQUALIFIED", wallet[:8] + "...")
                update_holder_sell(wallet, 0)
            except Exception as exc:
                errors += 1
                logger.error("Zero-exit update failed for %s: %s", wallet[:8] + "...", exc)

    logger.info(
        "Holder update complete — %d on-chain holders, %d errors",
        len(all_holders), errors,
    )


async def _process_wallet_with_balance(wallet: str, new_balance: int) -> None:
    """Update DB for one wallet given its already-fetched balance."""
    ensure_holder_exists(wallet)
    holder = get_holder(wallet)

    prev_balance: int = holder["current_balance"] if holder else 0
    prev_action: str = holder["last_action"] if holder and holder["last_action"] else ""

    if new_balance > prev_balance:
        is_fresh_buy = prev_action != "BUY"
        if is_fresh_buy:
            logger.info(
                "BUY (timer START): %s | %d → %d tokens",
                wallet[:8] + "...", prev_balance, new_balance,
            )
        else:
            logger.info(
                "BUY (top-up, timer unchanged): %s | %d → %d tokens",
                wallet[:8] + "...", prev_balance, new_balance,
            )
        update_holder_buy(wallet, new_balance)

    elif new_balance < prev_balance:
        logger.info(
            "SELL detected: %s | %d → %d tokens — DISQUALIFIED",
            wallet[:8] + "...", prev_balance, new_balance,
        )
        update_holder_sell(wallet, new_balance)

    else:
        update_holder_balance_no_change(wallet)
