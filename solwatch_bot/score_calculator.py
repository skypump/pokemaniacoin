from __future__ import annotations
"""
score_calculator.py — Pokemon evolution score system.

HOW IT WORKS:
  1. Hold time → evolution level (1–5). Every 15 min of holding = +1 level.
  2. Callout bonus doubles the multiplier.
  3. Score = balance × seconds_held × effective_multiplier
  4. Payout share = wallet_score / total_score_all_wallets

Evolution Levels (from hold time; requires MIN_HOLDER_BALANCE to be eligible):
   0–15 min  → Level 1  ×1
  15–30 min  → Level 2  ×2
  30–45 min  → Level 3  ×3
  45–60 min  → Level 4  ×4
     60 min+ → Level 5  ×5  (Mega form)
"""
import logging
import time

from config import settings
from db import get_all_active_holders, update_holder_score

logger = logging.getLogger(__name__)

# (min_seconds inclusive, max_seconds exclusive or None, level, display name)
_EVOLUTION_TIERS: list[tuple[int, int | None, int, str]] = [
    (0,    900,  1, "Level 1 — Base"),
    (900,  1800, 2, "Level 2"),
    (1800, 2700, 3, "Level 3"),
    (2700, 3600, 4, "Level 4"),
    (3600, None, 5, "Level 5 — Mega"),
]


def get_evolution_level(seconds_held: int) -> int:
    """Return evolution level 1–5 based on hold time in seconds."""
    for min_s, max_s, level, _ in _EVOLUTION_TIERS:
        if max_s is None or seconds_held < max_s:
            return level
    return 5


def get_evolution_name(seconds_held: int) -> str:
    """Return display name for current evolution level."""
    for min_s, max_s, _, name in _EVOLUTION_TIERS:
        if max_s is None or seconds_held < max_s:
            return name
    return "Level 5 — Mega"


def get_effective_multiplier(seconds_held: int, callout_verified: bool) -> float:
    """Score multiplier = evolution_level × (2 if callout_verified else 1)."""
    level = get_evolution_level(seconds_held)
    return float(level) * (2.0 if callout_verified else 1.0)


def compute_scores() -> int:
    """
    Persist scores for all active holders.
    Score = balance × seconds_held × effective_multiplier
    Returns number of holders scored.
    """
    holders = get_all_active_holders()
    if not holders:
        return 0

    now = int(time.time())
    for h in holders:
        balance = int(h["current_balance"])
        callout_verified = bool(h["callout_verified"])
        registered_at = int(h["registered_at"]) if h["registered_at"] else None
        if registered_at is None:
            continue  # not yet registered on frontend

        seconds_held = max(0, now - registered_at)
        multiplier = get_effective_multiplier(seconds_held, callout_verified)
        score = float(balance) * seconds_held * multiplier

        level_name = get_evolution_name(seconds_held)
        update_holder_score(h["wallet"], score, level_name)

    logger.debug("Scores computed for %d holders", len(holders))
    return len(holders)
