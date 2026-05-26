from __future__ import annotations
"""
demo_server.py — Fake API server for frontend preview.
Run with:  python demo_server.py
Open:      http://localhost:8000
"""
import math
import time
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
import os

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])

# Serve the frontend HTML
_web_dir = os.path.join(os.path.dirname(__file__), '..', 'solwatch_web')

@app.get("/")
async def index():
    return FileResponse(os.path.join(_web_dir, 'index.html'))

START       = time.time()
SHIFT_SEC   = 600        # 10-min real shift
DEMO_CYCLE  = 30         # seconds per demo cycle (speeds up 20×)
VAULT_MAX   = 94.20      # peak vault USD per demo cycle

WALLETS = [
    "7xKqMpN3...3RmP",
    "9aFwBcL7...8TnL",
    "Kp9sZrT2...2VxR",
    "Jr5dYnQ8...8MnT",
    "Tw2bXcP1...6LdH",
    "Bm3cHvS6...1PqY",
    "Rn7vDkW4...5HsQ",
    "Yx4dGjF9...9WkF",
    "CRb5M6rcCHzAUBaSzeB6nLmmdiTK9aKhDC7DFs57Kkyo",
]

DISQ_WALLETS = [
    "Zx1pQmR5...4KdR",
    "Hq8mVnT3...7WeV",
    "Lf6nCbS2...9TsB",
]

# (wallet_idx, bracket, base_rate, callout_verified, callout_bonus,
#  total_shifts_worked, current_streak, total_sol_earned, total_clicks_alltime, base_seconds_held)
HOLDER_META = [
    (0, "Bank Manager",    1.0, True,  1, 142, 31, 4.812, 38420, 7200),
    (1, "Bank Manager",    1.0, True,  1,  87, 22, 2.241, 24100, 5400),
    (2, "Head Teller",     0.5, True,  1,  54, 14, 1.108, 15730, 3600),
    (3, "Head Teller",     0.5, True,  1,  33,  8, 0.521,  9870, 2700),
    (4, "Senior Cashier",  0.2, False, 0,  19,  5, 0.198,  4320, 1800),
    (5, "Senior Cashier",  0.2, False, 0,   8,  3, 0.041,  1880, 1200),
    (6, "Cashier",         0.1, False, 0,   2,  1, 0.006,   340,  600),
    (7, "Cashier",         0.1, False, 0,   1,  1, 0.000,    80,  300),
    (8, "Head Teller",     0.5, True,  1,  12,  4, 0.310,  6500, 2400),
]

# Evolution thresholds in seconds: Lv1=0, Lv2=15min, Lv3=30min, Lv4=45min, Lv5=60min
_EVO_THRESHOLDS = [0, 900, 1800, 2700, 3600]

def _evolution_level(seconds_held: int) -> int:
    lv = 1
    for i, t in enumerate(_EVO_THRESHOLDS):
        if seconds_held >= t:
            lv = i + 1
    return min(lv, 5)

CALLOUT_TEXTS = [
    "hire me",
    "hire me — best holder fr fr",
    "hire me i never sell",
    "hire me diamond hands",
    "", "", "", "",
    "hire me",
]

BALANCES = [6_000_000, 5_200_000, 1_800_000, 1_100_000, 700_000, 520_000, 140_000, 110_000, 150_000]

# ── Submitted game clicks (reset each shift) ─────────────────────────────────
_demo_clicks: dict[str, int] = {}    # wallet -> clicks this shift
_demo_last_shift: int | None = None  # last shift number seen by state()
_demo_past_winners: list = []        # winner entries from completed shifts


def _settle_shift(completed_shift: int, vault_usd: float, sol_price: float) -> None:
    """Called when a new shift starts. Compute payouts for submitted wallets."""
    global _demo_clicks, _demo_past_winners
    if not _demo_clicks:
        return

    # Approximate total demo clicks for the completed shift
    demo_score = sum(
        int(HOLDER_META[i][2] * (2.0 if HOLDER_META[i][3] else 1.0) * SHIFT_SEC * 0.65)
        for i in range(len(HOLDER_META))
    )
    submitted_score = sum(_demo_clicks.values())
    grand_total = max(1, demo_score + submitted_score)

    now = int(time.time())
    per_sol = vault_usd / sol_price if sol_price > 0 else 0

    new_entries = []
    for wallet, clicks in _demo_clicks.items():
        if clicks <= 0:
            continue
        share = clicks / grand_total
        new_entries.append({
            "wallet":       wallet,
            "amount_sol":   round(per_sol * share, 6),
            "amount_usd":   round(vault_usd * share, 2),
            "tx_hash":      f"tx{completed_shift:04d}_{wallet[:6]}demo",
            "won_at":       now,
            "shift_number": completed_shift,
            "share_pct":    round(share * 100, 2),
        })

    _demo_past_winners = (new_entries + _demo_past_winners)[:24]
    _demo_clicks = {}


@app.get("/api/state")
async def state() -> JSONResponse:
    global _demo_last_shift

    now     = int(time.time())
    elapsed = time.time() - START
    t       = elapsed / DEMO_CYCLE

    # ── Shift timing ─────────────────────────────────────────────────────────
    time_in_cycle   = elapsed % DEMO_CYCLE
    frac            = time_in_cycle / DEMO_CYCLE
    secs_left       = int((1 - frac) * SHIFT_SEC)
    shift_elapsed   = SHIFT_SEC - secs_left
    shift_number    = int(elapsed / DEMO_CYCLE) + 1
    shifts_done     = shift_number - 1

    # ── Price & vault ─────────────────────────────────────────────────────────
    sol_price      = round(148.32 + 4 * math.sin(elapsed / 45), 2)
    vault_usd      = round(frac * VAULT_MAX + 2 * abs(math.sin(elapsed * 0.2)), 2)
    vault_lamports = int(vault_usd / sol_price * 1e9) if sol_price else 0
    total_usd      = round(shifts_done * VAULT_MAX * 0.97, 2)

    # ── Detect shift rollover → settle submitted clicks from last shift ───────
    if _demo_last_shift is None:
        _demo_last_shift = shift_number
    elif shift_number > _demo_last_shift:
        _settle_shift(_demo_last_shift, round(VAULT_MAX * 0.95, 2), sol_price)
        _demo_last_shift = shift_number

    # ── Available clicks per wallet (rate × elapsed seconds this shift) ───────
    def available(base_rate: float, callout: bool) -> int:
        rate = base_rate * (2.0 if callout else 1.0)
        return int(rate * shift_elapsed)

    # Score = actual clicks used (animated fraction of available) ─────────────
    def used_clicks(avail: int, i: int) -> int:
        pct = 0.55 + 0.35 * abs(math.sin(t * (0.7 + i * 0.15) + i))
        return int(avail * pct)

    # ── Build demo eligible list ──────────────────────────────────────────────
    eligible = []
    for i, (_, bracket, base_rate, callout_verified, callout_bonus,
            total_shifts, streak, total_sol, total_clicks_at, base_secs) in enumerate(HOLDER_META):
        eff_rate    = base_rate * (2.0 if callout_verified else 1.0)
        avail       = available(base_rate, callout_verified)
        score       = used_clicks(avail, i)
        secs_held   = base_secs + shift_elapsed
        evo_lv      = _evolution_level(secs_held)
        eff_mult    = evo_lv * (2.0 if callout_verified else 1.0)
        eligible.append({
            "wallet":               WALLETS[i],
            "score":                score,
            "balance":              BALANCES[i],
            "bracket":              bracket,
            "click_rate":           eff_rate,
            "available_clicks":     avail,
            "callout_verified":     callout_verified,
            "callout_bonus":        callout_bonus,
            "callout_text":         CALLOUT_TEXTS[i],
            "shift_clicks":         score,
            "total_clicks_alltime": total_clicks_at + score,
            "total_shifts_worked":  total_shifts,
            "current_streak":       streak,
            "total_sol_earned":     round(total_sol, 6),
            "seconds_held":         secs_held,
            "evolution_level":      evo_lv,
            "effective_multiplier": eff_mult,
            "share_pct":            0.0,
            "chance_pct":           0.0,
            "estimated_payout_usd": 0.0,
        })

    # ── Merge submitted game clicks ───────────────────────────────────────────
    for wallet, clicks in _demo_clicks.items():
        if clicks <= 0:
            continue
        existing = next((e for e in eligible if e["wallet"] == wallet), None)
        if existing:
            existing["score"]        = clicks
            existing["shift_clicks"] = clicks
        else:
            avail_sub = max(clicks, int(0.1 * shift_elapsed))
            eligible.append({
                "wallet":               wallet,
                "score":                clicks,
                "balance":              100_000,
                "bracket":              "Cashier",
                "click_rate":           0.1,
                "available_clicks":     avail_sub,
                "callout_verified":     False,
                "callout_bonus":        0,
                "callout_text":         "",
                "shift_clicks":         clicks,
                "total_clicks_alltime": clicks,
                "total_shifts_worked":  0,
                "current_streak":       0,
                "total_sol_earned":     0.0,
                "share_pct":            0.0,
                "chance_pct":           0.0,
                "estimated_payout_usd": 0.0,
            })

    # ── Recompute share percentages after merge ───────────────────────────────
    total_score = sum(e["score"] for e in eligible) or 1
    for e in eligible:
        share = e["score"] / total_score
        e["share_pct"]            = round(share * 100, 2)
        e["chance_pct"]           = e["share_pct"]
        e["estimated_payout_usd"] = round(share * vault_usd, 2)
        # Add vault share to total_sol_earned for demo wallets
        w_idx = next((j for j, w in enumerate(WALLETS) if w == e["wallet"]), None)
        if w_idx is not None:
            e["total_sol_earned"] = round(
                HOLDER_META[w_idx][7] + share * vault_lamports / 1e9, 6
            )

    eligible.sort(key=lambda h: h["score"], reverse=True)

    # ── Disqualified ──────────────────────────────────────────────────────────
    disqualified = [
        {
            "wallet":        DISQ_WALLETS[0],
            "callout_text":  "hire me",
            "callout_bonus": 1,
            "reason":        "sold",
            "sold_at":       now - 420,
        },
        {
            "wallet":        DISQ_WALLETS[1],
            "callout_text":  "hire me or else",
            "callout_bonus": 0,
            "reason":        "sold",
            "sold_at":       now - 1800,
        },
        {
            "wallet":        DISQ_WALLETS[2],
            "callout_text":  "gm hire me",
            "callout_bonus": 0,
            "reason":        "wrong phrase",
            "sold_at":       None,
        },
    ]

    # ── Recent winners: demo history + submitted wallet winners ───────────────
    demo_winners = []
    for s in range(min(8, shifts_done)):
        sn        = shifts_done - s
        vault_s   = round(VAULT_MAX * 0.92 + 4 * math.sin(s * 1.3), 2)
        per_sol   = vault_s / sol_price
        top_share = 0.35 + 0.05 * math.sin(s * 0.7)
        for rank in range(3):
            share   = top_share / (1 + rank)
            amt_usd = round(vault_s * share, 2)
            demo_winners.append({
                "wallet":       WALLETS[(sn + rank) % len(WALLETS)],
                "amount_sol":   round(per_sol * share, 6),
                "amount_usd":   amt_usd,
                "tx_hash":      f"tx{sn:04d}r{rank}demo",
                "won_at":       now - s * int(SHIFT_SEC * 1.02) - rank * 2,
                "shift_number": sn,
                "share_pct":    round(share * 100, 2),
            })

    all_winners = demo_winners + _demo_past_winners
    all_winners.sort(key=lambda w: w.get("won_at", 0), reverse=True)
    recent_winners = all_winners[:20]

    mint = "7H4fXpLmN9qRtBs3WcKdYvP2eAuJoZkMxNwFgQhDrCp" if elapsed > 5 else None

    return JSONResponse({
        "shift_number":              shift_number,
        "shift_interval_seconds":    SHIFT_SEC,
        "next_airdrop_in_seconds":   secs_left,
        "seconds_until_shift_end":   secs_left,
        "shift_elapsed_seconds":     shift_elapsed,

        "prize_pool_usd":            vault_usd,
        "shift_vault_usd":           vault_usd,
        "shift_vault_lamports":      vault_lamports,

        "airdrops_given":            shifts_done,
        "shifts_completed":          shifts_done,
        "total_distributed_usd":     total_usd,
        "sol_price_usd":             sol_price,

        "mint_address":              mint,
        "magic_phrase":              "hire me",
        "min_holder_balance":        100000,
        "click_weight":              1000,

        "eligible_holders":          eligible,
        "active_workers_count":      len(eligible),
        "disqualified":              disqualified,

        "recent_winners":            recent_winners,
    })


# ── Game score endpoint ───────────────────────────────────────────────────────

class GameScorePayload(BaseModel):
    wallet: str
    clicks: int


@app.post("/api/game/score")
async def post_game_score(payload: GameScorePayload) -> dict:
    _demo_clicks[payload.wallet] = _demo_clicks.get(payload.wallet, 0) + payload.clicks
    return {
        "ok":          True,
        "wallet":      payload.wallet,
        "added":       payload.clicks,
        "shift_clicks": _demo_clicks[payload.wallet],
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "demo", "timestamp": int(time.time())}


if __name__ == "__main__":
    print()
    print("  $BANKER DEMO server — http://127.0.0.1:8000")
    print("  Open: solwatch_web/index.html")
    print()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning", access_log=False)
