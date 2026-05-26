"""
reward_tracker.py — Log deploy wallet balance changes for visibility.

The prize counter is NO LONGER updated here.
It is updated exclusively in collect_loop (main.py) based on the exact
lamports pulled from the creator vault — which is the only correct source.

This file only exists to give you a log line when your wallet balance
changes, so you can see payouts and unexpected movements.
"""
import logging

from db import get_last_deploy_balance_lamports, set_last_deploy_balance_lamports
from solana_client import get_deploy_wallet_sol_balance

logger = logging.getLogger(__name__)


async def poll_deploy_balance() -> None:
    """
    Snapshot the deploy wallet balance and log any changes.
    Does NOT touch the prize counter.
    """
    try:
        current_lamports = await get_deploy_wallet_sol_balance()
    except Exception as exc:
        logger.error("Failed to fetch deploy wallet balance: %s", exc)
        return

    prev_lamports = get_last_deploy_balance_lamports()

    if current_lamports > prev_lamports:
        delta = current_lamports - prev_lamports
        logger.info(
            "Deploy wallet +%.6f SOL (balance now %.6f SOL)",
            delta / 1e9, current_lamports / 1e9,
        )
    elif current_lamports < prev_lamports:
        delta = prev_lamports - current_lamports
        logger.info(
            "Deploy wallet -%.6f SOL (payout or withdrawal — balance now %.6f SOL)",
            delta / 1e9, current_lamports / 1e9,
        )

    set_last_deploy_balance_lamports(current_lamports)
