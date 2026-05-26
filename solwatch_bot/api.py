"""
api.py — FastAPI server for the $PKMN Pokemon evolution dashboard.
"""
import time
import logging
import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from db import (
    _assign_pokemon,
    get_callout_for_wallet,
    get_conn,
    get_disqualified_holders,
    get_eligible_holders,
    get_holder,
    get_recent_winners,
    get_shift_number,
    get_shift_started_at,
    get_shift_vault_lamports,
    get_watches_given,
    get_total_distributed_usd,
    register_holder,
    seconds_until_shift_end,
)
from price_oracle import get_sol_price_usd, lamports_to_usd
from score_calculator import get_evolution_level, get_evolution_name, get_effective_multiplier
from mint_detector import mint_is_configured

logger = logging.getLogger(__name__)

app = FastAPI(title="$PKMN Bot API", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_WEB_DIR = os.path.join(os.path.dirname(__file__), "..", "solwatch_web")


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(os.path.join(_WEB_DIR, "index.html"))

# Pokemon metadata (index 0 = unused, 1/2/3 = fire/water/grass)
_POKEMON = [
    None,
    {"id": 1, "name": "Embyr",    "type": "fire",  "role": "The Grinder"},
    {"id": 2, "name": "Tidalin",  "type": "water", "role": "The Hodler"},
    {"id": 3, "name": "Sproutly", "type": "grass", "role": "The Whale"},
]

_LEVEL_EMOJIS = {0: "🥚", 1: "🐣", 2: "🐥", 3: "⭐", 4: "🌟", 5: "💥"}


@app.get("/api/state")
async def get_state() -> JSONResponse:
    try:
        sol_price = await get_sol_price_usd()
    except Exception:
        sol_price = 0.0

    vault_lamports = get_shift_vault_lamports()
    vault_usd = lamports_to_usd(vault_lamports, sol_price) if sol_price else 0.0

    secs_left = seconds_until_shift_end()
    shift_interval = settings.SHIFT_INTERVAL_SECONDS
    elapsed = shift_interval - secs_left
    shift_number = get_shift_number()
    shifts_given = get_watches_given()
    total_usd = get_total_distributed_usd()

    eligible_rows = get_eligible_holders()
    total_score = sum(float(h["score"]) for h in eligible_rows) or 1.0

    shift_start = get_shift_started_at()
    now = int(time.time())

    eligible_list = []
    for h in eligible_rows:
        balance = int(h["current_balance"])
        callout_verified = bool(h["callout_verified"])
        registered_at = int(h["registered_at"]) if h["registered_at"] else None
        seconds_held = max(0, now - registered_at) if registered_at else 0

        evolution_level = get_evolution_level(seconds_held)
        evolution_name = get_evolution_name(seconds_held)
        multiplier = get_effective_multiplier(seconds_held, callout_verified)
        pokemon_id = int(h["pokemon_id"]) if h["pokemon_id"] else _assign_pokemon(h["wallet"])
        pokemon = _POKEMON[pokemon_id] if 1 <= pokemon_id <= 3 else _POKEMON[1]

        score = float(h["score"])
        eligible_list.append({
            "wallet": h["wallet"],
            "score": round(score, 0),
            "share_pct": round(score / total_score * 100, 2),
            "balance": balance,
            "seconds_held": seconds_held,
            "evolution_level": evolution_level,
            "evolution_name": evolution_name,
            "evolution_emoji": _LEVEL_EMOJIS.get(evolution_level, "🐣"),
            "effective_multiplier": multiplier,
            "callout_verified": callout_verified,
            "pokemon_id": pokemon_id,
            "pokemon_name": pokemon["name"],
            "pokemon_type": pokemon["type"],
            "pokemon_role": pokemon["role"],
            "total_shifts_worked": int(h["total_shifts_worked"]),
            "current_streak": int(h["current_streak"]),
            "total_sol_earned": round(float(h["total_sol_earned"]), 6),
            "estimated_payout_usd": round(score / total_score * vault_usd, 2),
            # kept for backwards compat
            "bracket": evolution_name,
            "chance_pct": round(score / total_score * 100, 1),
        })

    disq_rows = get_disqualified_holders()
    disq_list = [
        {
            "wallet": h["wallet"],
            "callout_verified": bool(h["callout_verified"]),
            "reason": "sold",
            "sold_at": h["disqualified_at"],
            "pokemon_id": int(h["pokemon_id"]) if h["pokemon_id"] else _assign_pokemon(h["wallet"]),
        }
        for h in disq_rows
    ]

    winner_rows = get_recent_winners(20)
    winners_list = [
        {
            "wallet": w["wallet"],
            "amount_sol": round(float(w["amount_sol"]), 6),
            "amount_usd": round(float(w["amount_usd"]), 2),
            "tx_hash": w["tx_hash"],
            "won_at": w["won_at"],
            "shift_number": w["shift_number"],
            "share_pct": round(float(w["share_pct"]), 2),
        }
        for w in winner_rows
    ]

    mint = settings.SOLWATCH_MINT_ADDRESS if mint_is_configured() else None

    payload: dict[str, Any] = {
        "shift_number": shift_number,
        "shift_interval_seconds": shift_interval,
        "seconds_until_shift_end": secs_left,
        "next_airdrop_in_seconds": secs_left,  # legacy alias
        "shift_elapsed_seconds": elapsed,
        "prize_pool_usd": round(vault_usd, 2),
        "shift_vault_usd": round(vault_usd, 2),
        "shift_vault_lamports": vault_lamports,
        "airdrops_given": shifts_given,
        "shifts_completed": shifts_given,
        "total_distributed_usd": round(total_usd, 2),
        "sol_price_usd": round(sol_price, 2),
        "mint_address": mint,
        "magic_phrase": settings.MAGIC_PHRASE,
        "min_holder_balance": settings.MIN_HOLDER_BALANCE,
        "eligible_holders": eligible_list,
        "active_workers_count": len(eligible_list),
        "disqualified": disq_list,
        "recent_winners": winners_list,
        "pokemon_config": {
            "names": settings.POKEMON_NAMES,
            "types": settings.POKEMON_TYPES,
            "evolution_thresholds": settings.EVOLUTION_THRESHOLDS,
        },
    }

    return JSONResponse(content=payload)


from pydantic import BaseModel

class RegisterPayload(BaseModel):
    wallet: str

@app.post("/api/register")
async def register_wallet(payload: RegisterPayload) -> dict:
    wallet = payload.wallet.strip()
    if not wallet:
        return JSONResponse({"ok": False, "error": "missing wallet"}, status_code=400)
    holder = get_holder(wallet)
    if not holder or int(holder["current_balance"]) < settings.MIN_HOLDER_BALANCE:
        return JSONResponse({"ok": False, "error": "not_holder"}, status_code=200)
    register_holder(wallet)
    return {"ok": True, "wallet": wallet}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": int(time.time()), "shift": get_shift_number()}
