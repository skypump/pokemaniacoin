"""
draw.py — Pro-rata SOL shift distribution every SHIFT_INTERVAL_SECONDS.

Every 10 minutes (one shift):
  1. Snapshot all eligible workers and their scores.
  2. Distribute the entire shift vault pro-rata: each worker gets
         payout = (their_score / total_score) × vault_lamports
  3. Reset shift vault to 0 and per-shift click counters.
  4. Increment shift number and record payouts.

This replaces the old weighted lottery. Everyone with score > 0 earns
something every shift — proportional to bag size, hold tier, callout
bonus, and how many bills they grabbed in the clicker game.

TODO: swap vault SOL → USDC via Jupiter v6 before distributing.
"""
import asyncio
import logging
import time

from config import settings
from db import (
    add_total_distributed_usd,
    finalize_shift_for_workers,
    get_eligible_holders,
    get_shift_number,
    get_shift_vault_lamports,
    increment_watches_given,
    record_winner,
    reset_all_shift_clicks,
    seconds_until_shift_end,
    set_shift_vault_lamports,
    start_new_shift,
)
from price_oracle import get_sol_price_usd, lamports_to_usd
from solana_client import get_deploy_wallet_sol_balance, send_sol
from score_calculator import compute_scores

logger = logging.getLogger(__name__)

_shift_in_progress = False


async def check_and_execute_shift() -> None:
    """
    Called every DRAW_CHECK_INTERVAL seconds.
    Executes shift end when SHIFT_INTERVAL_SECONDS have elapsed.
    """
    global _shift_in_progress
    if _shift_in_progress:
        return
    if seconds_until_shift_end() > 0:
        return

    try:
        sol_price = await get_sol_price_usd()
    except Exception as exc:
        logger.error("Shift end: SOL price unavailable — skipping: %s", exc)
        # Still need to advance the shift timer so we don't get stuck
        start_new_shift()
        return

    vault_lamports = get_shift_vault_lamports()

    _shift_in_progress = True
    try:
        await _execute_shift(vault_lamports, sol_price)
    except Exception as exc:
        logger.error("Shift execution error: %s", exc)
    finally:
        _shift_in_progress = False


async def _execute_shift(vault_lamports: int, sol_price: float) -> None:
    shift_num = get_shift_number()
    vault_usd = lamports_to_usd(vault_lamports, sol_price)

    logger.info("=" * 60)
    logger.info("SHIFT #%d END — vault: %.6f SOL ($%.2f)", shift_num, vault_lamports / 1e9, vault_usd)

    compute_scores()
    eligible = get_eligible_holders()

    if not eligible:
        logger.info("Shift #%d: no eligible workers — vault rolls over to next shift", shift_num)
        increment_watches_given()
        start_new_shift()
        return

    total_score = sum(float(h["score"]) for h in eligible)
    if total_score <= 0:
        logger.info("Shift #%d: total score is 0 — vault rolls over", shift_num)
        increment_watches_given()
        start_new_shift()
        return

    if vault_lamports < settings.TX_FEE_BUFFER_LAMPORTS * len(eligible):
        logger.warning(
            "Shift #%d: vault too small (%.6f SOL) for %d workers — rolling over",
            shift_num, vault_lamports / 1e9, len(eligible),
        )
        increment_watches_given()
        start_new_shift()
        return

    deploy_balance = await get_deploy_wallet_sol_balance()
    if deploy_balance < vault_lamports:
        logger.error(
            "Shift #%d: INSUFFICIENT FUNDS in deploy wallet (%.6f SOL < %.6f SOL needed)",
            shift_num, deploy_balance / 1e9, vault_lamports / 1e9,
        )
        start_new_shift()
        return

    # ── Pro-rata distribution ─────────────────────────────────────────────────
    paid_wallets: list[str] = []
    total_paid_lamports = 0

    for holder in eligible:
        share = float(holder["score"]) / total_score
        payout_lamports = int(vault_lamports * share)

        # Skip dust payouts that don't cover the tx fee buffer
        if payout_lamports < settings.TX_FEE_BUFFER_LAMPORTS * 2:
            continue

        net_lamports = payout_lamports - settings.TX_FEE_BUFFER_LAMPORTS
        payout_sol = net_lamports / 1e9
        payout_usd = lamports_to_usd(net_lamports, sol_price)
        share_pct = share * 100

        logger.info(
            "  Paying %s — score=%.0f (%.1f%%) — %.6f SOL ($%.2f)",
            holder["wallet"][:8] + "...",
            float(holder["score"]), share_pct, payout_sol, payout_usd,
        )

        try:
            tx_hash = await send_sol(holder["wallet"], net_lamports)
        except Exception as exc:
            logger.error("  Transfer FAILED for %s: %s", holder["wallet"][:8] + "...", exc)
            continue

        record_winner(
            wallet=holder["wallet"],
            amount_sol=round(payout_sol, 6),
            amount_usd=round(payout_usd, 2),
            tx_hash=tx_hash,
            shift_number=shift_num,
            share_pct=share_pct,
        )
        add_total_distributed_usd(payout_usd)
        paid_wallets.append(holder["wallet"])
        total_paid_lamports += net_lamports

    increment_watches_given()

    # ── Finalize shift ────────────────────────────────────────────────────────
    # Deduct only what was actually paid; remainder rolls into next shift
    remaining = max(0, vault_lamports - total_paid_lamports)
    set_shift_vault_lamports(remaining)

    reset_all_shift_clicks()
    finalize_shift_for_workers(paid_wallets)
    new_shift = start_new_shift()

    total_paid_usd = lamports_to_usd(total_paid_lamports, sol_price)
    logger.info(
        "SHIFT #%d COMPLETE — paid %d/%d workers, %.6f SOL ($%.2f) | "
        "vault remaining %.6f SOL | shift #%d started",
        shift_num, len(paid_wallets), len(eligible),
        total_paid_lamports / 1e9, total_paid_usd,
        remaining / 1e9, new_shift,
    )
    logger.info("=" * 60)


# ── Legacy alias so old imports don't break ───────────────────────────────────

async def check_and_execute_draw() -> None:
    await check_and_execute_shift()


def force_draw_cli() -> None:
    """Manual override: force shift end immediately.
    Usage: python -c "from draw import force_draw_cli; force_draw_cli()"
    """
    print("Force shift end triggered")
    asyncio.run(check_and_execute_shift())
