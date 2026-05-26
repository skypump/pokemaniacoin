"""
db.py — SQLite schema + all database helper functions.
All timestamps are UTC unix integers. All SOL amounts are lamports internally.
"""
import sqlite3
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = "solwatch.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create all tables and run any missing migrations. Safe to call every startup."""
    conn = get_conn()

    # ── Migrations: add new columns to existing tables ────────────────────────
    # Each ALTER is wrapped in try/except — SQLite has no IF NOT EXISTS for ALTER.
    _migrations = [
        ("holders", "game_clicks",          "INTEGER NOT NULL DEFAULT 0"),
        ("holders", "callout_verified",     "INTEGER NOT NULL DEFAULT 0"),
        ("holders", "callout_bonus",        "INTEGER NOT NULL DEFAULT 0"),
        ("holders", "current_time_tier",    "TEXT NOT NULL DEFAULT 'New Hire'"),
        ("holders", "shift_clicks",         "INTEGER NOT NULL DEFAULT 0"),
        ("holders", "total_shifts_worked",  "INTEGER NOT NULL DEFAULT 0"),
        ("holders", "current_streak",       "INTEGER NOT NULL DEFAULT 0"),
        ("holders", "total_clicks_alltime", "INTEGER NOT NULL DEFAULT 0"),
        ("holders", "total_sol_earned",     "REAL NOT NULL DEFAULT 0.0"),
        ("holders", "pokemon_id",           "INTEGER NOT NULL DEFAULT 0"),
        ("holders", "evolution_level",      "INTEGER NOT NULL DEFAULT 1"),
        ("holders", "registered_at",        "INTEGER"),
        ("winners", "shift_number",         "INTEGER NOT NULL DEFAULT 0"),
        ("winners", "share_pct",            "REAL NOT NULL DEFAULT 0.0"),
    ]
    for table, col, definition in _migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")
            conn.commit()
        except Exception:
            pass  # column already exists

    # ── Core tables ───────────────────────────────────────────────────────────
    with conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS callouts (
                wallet              TEXT NOT NULL,
                callout_text        TEXT NOT NULL,
                callout_timestamp   INTEGER NOT NULL,
                has_magic_phrase    INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (wallet, callout_timestamp)
            );

            CREATE TABLE IF NOT EXISTS holders (
                wallet              TEXT PRIMARY KEY,
                current_balance     INTEGER NOT NULL DEFAULT 0,
                last_buy_time       INTEGER,
                last_action         TEXT,
                eligible            INTEGER NOT NULL DEFAULT 0,
                score               REAL NOT NULL DEFAULT 0.0,
                game_clicks         INTEGER NOT NULL DEFAULT 0,
                disqualified_at     INTEGER,
                updated_at          INTEGER NOT NULL DEFAULT 0,
                callout_verified    INTEGER NOT NULL DEFAULT 0,
                callout_bonus       INTEGER NOT NULL DEFAULT 0,
                current_time_tier   TEXT NOT NULL DEFAULT 'New Hire',
                shift_clicks        INTEGER NOT NULL DEFAULT 0,
                total_shifts_worked INTEGER NOT NULL DEFAULT 0,
                current_streak      INTEGER NOT NULL DEFAULT 0,
                total_clicks_alltime INTEGER NOT NULL DEFAULT 0,
                total_sol_earned    REAL NOT NULL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS winners (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet      TEXT NOT NULL,
                amount_sol  REAL NOT NULL,
                amount_usd  REAL NOT NULL,
                tx_hash     TEXT NOT NULL,
                won_at      INTEGER NOT NULL,
                shift_number INTEGER NOT NULL DEFAULT 0,
                share_pct   REAL NOT NULL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS bot_state (
                key     TEXT PRIMARY KEY,
                value   TEXT NOT NULL
            );
        """)

    conn.close()
    logger.info("Database initialised at %s", DB_PATH)


# ── bot_state helpers ─────────────────────────────────────────────────────────

def state_get(key: str, default: str = "0") -> str:
    conn = get_conn()
    row = conn.execute("SELECT value FROM bot_state WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def state_set(key: str, value: str) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO bot_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
    conn.close()


# ── Shift vault (SOL collected this shift) ────────────────────────────────────

def get_shift_vault_lamports() -> int:
    return int(state_get("shift_vault_lamports", "0"))


def set_shift_vault_lamports(val: int) -> None:
    state_set("shift_vault_lamports", str(max(0, val)))


def add_to_shift_vault(lamports: int) -> int:
    new_val = get_shift_vault_lamports() + lamports
    set_shift_vault_lamports(new_val)
    return new_val


# ── Shift number / timing ─────────────────────────────────────────────────────

def get_shift_number() -> int:
    return int(state_get("shift_number", "0"))


def get_shift_started_at() -> int:
    return int(state_get("shift_started_at", str(int(time.time()))))


def start_new_shift() -> int:
    """Increment shift counter, record start time. Returns new shift number."""
    new_num = get_shift_number() + 1
    state_set("shift_number", str(new_num))
    state_set("shift_started_at", str(int(time.time())))
    return new_num


def seconds_until_shift_end() -> int:
    from config import settings
    elapsed = int(time.time()) - get_shift_started_at()
    return max(0, settings.SHIFT_INTERVAL_SECONDS - elapsed)


# ── Legacy helpers kept for backward compat ───────────────────────────────────

def get_prize_counter_lamports() -> int:
    return get_shift_vault_lamports()


def set_prize_counter_lamports(val: int) -> None:
    set_shift_vault_lamports(val)


def get_last_draw_time() -> int:
    return get_shift_started_at()


def set_last_draw_time(val: int) -> None:
    state_set("shift_started_at", str(val))


def get_watches_given() -> int:
    return int(state_get("watches_given", "0"))


def increment_watches_given() -> None:
    state_set("watches_given", str(get_watches_given() + 1))


def get_total_distributed_usd() -> float:
    return float(state_get("total_distributed_usd", "0.0"))


def add_total_distributed_usd(amount: float) -> None:
    state_set("total_distributed_usd", str(round(get_total_distributed_usd() + amount, 4)))


def get_last_deploy_balance_lamports() -> int:
    return int(state_get("last_deploy_balance_lamports", "0"))


def set_last_deploy_balance_lamports(val: int) -> None:
    state_set("last_deploy_balance_lamports", str(val))


# ── Callout helpers ───────────────────────────────────────────────────────────

def upsert_callout(wallet: str, text: str, timestamp: int, has_magic: bool) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO callouts "
            "(wallet, callout_text, callout_timestamp, has_magic_phrase) VALUES (?, ?, ?, ?)",
            (wallet, text, timestamp, int(has_magic)),
        )
    conn.close()


def get_wallets_with_magic_phrase() -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT wallet FROM callouts WHERE has_magic_phrase=1"
    ).fetchall()
    conn.close()
    return [r["wallet"] for r in rows]


def get_callout_for_wallet(wallet: str) -> Optional[sqlite3.Row]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM callouts WHERE wallet=? AND has_magic_phrase=1 "
        "ORDER BY callout_timestamp ASC LIMIT 1",
        (wallet,),
    ).fetchone()
    conn.close()
    return row


def try_verify_callout_bonus(wallet: str, min_balance: int) -> bool:
    """
    If wallet posted the magic phrase, holds >= min_balance, and hasn't been
    verified yet: mark callout_verified=1, callout_bonus=1.
    Returns True if newly verified.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT callout_verified, current_balance FROM holders WHERE wallet=?",
        (wallet,),
    ).fetchone()
    if not row:
        conn.close()
        return False
    if row["callout_verified"]:
        conn.close()
        return False  # already done
    if row["current_balance"] < min_balance:
        conn.close()
        return False

    has_magic = conn.execute(
        "SELECT 1 FROM callouts WHERE wallet=? AND has_magic_phrase=1 LIMIT 1",
        (wallet,),
    ).fetchone()
    if not has_magic:
        conn.close()
        return False

    with conn:
        conn.execute(
            "UPDATE holders SET callout_verified=1, callout_bonus=1 WHERE wallet=?",
            (wallet,),
        )
    conn.close()
    return True


# ── Holder helpers ────────────────────────────────────────────────────────────

def _assign_pokemon(wallet: str) -> int:
    """Deterministically assign Pokemon 1/2/3 from last wallet char."""
    c = wallet[-1].lower()
    if c.isdigit():
        return 1  # Fire type
    if c in "abcdefghi":
        return 2  # Water type
    return 3      # Grass type


def ensure_holder_exists(wallet: str) -> None:
    pokemon_id = _assign_pokemon(wallet)
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO holders (wallet, updated_at, pokemon_id) VALUES (?, ?, ?)",
            (wallet, int(time.time()), pokemon_id),
        )
    conn.close()


def get_holder(wallet: str) -> Optional[sqlite3.Row]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM holders WHERE wallet=?", (wallet,)).fetchone()
    conn.close()
    return row


def update_holder_buy(wallet: str, new_balance: int) -> None:
    now = int(time.time())
    conn = get_conn()
    with conn:
        conn.execute(
            """
            UPDATE holders
            SET current_balance=?,
                last_buy_time = CASE WHEN last_action='BUY' THEN last_buy_time ELSE ? END,
                last_action='BUY',
                eligible=1,
                disqualified_at=NULL,
                updated_at=?
            WHERE wallet=?
            """,
            (new_balance, now, now, wallet),
        )
    conn.close()


def update_holder_sell(wallet: str, new_balance: int) -> None:
    """Sell resets time tier (clock_in resets on next buy) but NOT callout_bonus."""
    now = int(time.time())
    conn = get_conn()
    with conn:
        conn.execute(
            """
            UPDATE holders
            SET current_balance=?,
                last_action='SELL',
                eligible=0,
                score=0.0,
                current_time_tier='New Hire',
                current_streak=0,
                disqualified_at=?,
                updated_at=?
            WHERE wallet=?
            """,
            (new_balance, now, now, wallet),
        )
    conn.close()


def update_holder_balance_no_change(wallet: str) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            "UPDATE holders SET updated_at=? WHERE wallet=?",
            (int(time.time()), wallet),
        )
    conn.close()


def update_holder_score(wallet: str, score: float, tier_name: str) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            "UPDATE holders SET score=?, current_time_tier=? WHERE wallet=?",
            (score, tier_name, wallet),
        )
    conn.close()


# ── Shift clicks ──────────────────────────────────────────────────────────────

def add_shift_clicks(wallet: str, clicks: int) -> int:
    """Add clicks to current shift total. Returns new shift_clicks count."""
    conn = get_conn()
    with conn:
        conn.execute(
            "UPDATE holders SET shift_clicks = shift_clicks + ? WHERE wallet=?",
            (max(0, clicks), wallet),
        )
    row = conn.execute("SELECT shift_clicks FROM holders WHERE wallet=?", (wallet,)).fetchone()
    conn.close()
    return int(row["shift_clicks"]) if row else 0


def get_shift_clicks(wallet: str) -> int:
    conn = get_conn()
    row = conn.execute("SELECT shift_clicks FROM holders WHERE wallet=?", (wallet,)).fetchone()
    conn.close()
    return int(row["shift_clicks"]) if row else 0


def reset_all_shift_clicks() -> None:
    """Called at shift end: archive shift_clicks into total_clicks_alltime, then zero out."""
    conn = get_conn()
    with conn:
        conn.execute(
            "UPDATE holders SET "
            "total_clicks_alltime = total_clicks_alltime + shift_clicks, "
            "game_clicks = game_clicks + shift_clicks, "
            "shift_clicks = 0"
        )
    conn.close()


def get_eligible_wallets() -> list[str]:
    """Return all wallets currently marked eligible=1 in the DB."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT wallet FROM holders WHERE eligible=1"
    ).fetchall()
    conn.close()
    return [r["wallet"] for r in rows]


# Legacy game_clicks helpers (used by old API endpoint)
def add_game_clicks(wallet: str, clicks: int) -> int:
    return add_shift_clicks(wallet, clicks)


def get_game_clicks(wallet: str) -> int:
    return get_shift_clicks(wallet)


# ── Eligible / disqualified queries ──────────────────────────────────────────

def get_eligible_holders() -> list[sqlite3.Row]:
    """Holders with enough balance and registered on the frontend."""
    from config import settings
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM holders WHERE eligible=1 "
        "AND current_balance >= ? AND registered_at IS NOT NULL ORDER BY score DESC",
        (settings.MIN_HOLDER_BALANCE,),
    ).fetchall()
    conn.close()
    return rows


def get_all_active_holders() -> list[sqlite3.Row]:
    """Registered holders with last_action=BUY and enough balance (for score computation)."""
    from config import settings
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM holders WHERE eligible=1 AND last_action='BUY' "
        "AND current_balance >= ? AND registered_at IS NOT NULL",
        (settings.MIN_HOLDER_BALANCE,),
    ).fetchall()
    conn.close()
    return rows


def register_holder(wallet: str) -> None:
    """Mark wallet as registered — timer starts now. Idempotent: only sets once."""
    now = int(time.time())
    conn = get_conn()
    with conn:
        conn.execute(
            "UPDATE holders SET registered_at=? WHERE wallet=? AND registered_at IS NULL",
            (now, wallet),
        )
    conn.close()


def get_disqualified_holders() -> list[sqlite3.Row]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM holders WHERE eligible=0 AND last_action='SELL'"
    ).fetchall()
    conn.close()
    return rows


# ── Shift end operations ──────────────────────────────────────────────────────

def finalize_shift_for_workers(worker_wallets: list[str]) -> None:
    """
    At shift end: increment total_shifts_worked and current_streak for
    every wallet that participated (had score > 0) this shift.
    """
    if not worker_wallets:
        return
    conn = get_conn()
    with conn:
        placeholders = ",".join("?" * len(worker_wallets))
        # Increment workers who participated
        conn.execute(
            f"UPDATE holders SET "
            f"total_shifts_worked = total_shifts_worked + 1, "
            f"current_streak = current_streak + 1 "
            f"WHERE wallet IN ({placeholders})",
            worker_wallets,
        )
        # Reset streak for eligible holders who did NOT participate
        conn.execute(
            f"UPDATE holders SET current_streak = 0 "
            f"WHERE eligible=1 AND wallet NOT IN ({placeholders})",
            worker_wallets,
        )
    conn.close()


# ── Winners helpers ───────────────────────────────────────────────────────────

def record_winner(
    wallet: str,
    amount_sol: float,
    amount_usd: float,
    tx_hash: str,
    shift_number: int = 0,
    share_pct: float = 0.0,
) -> None:
    conn = get_conn()
    with conn:
        conn.execute(
            "INSERT INTO winners "
            "(wallet, amount_sol, amount_usd, tx_hash, won_at, shift_number, share_pct) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (wallet, amount_sol, amount_usd, tx_hash,
             int(time.time()), shift_number, round(share_pct, 4)),
        )
        # Update lifetime SOL earned for this wallet
        conn.execute(
            "UPDATE holders SET total_sol_earned = total_sol_earned + ? WHERE wallet=?",
            (amount_sol, wallet),
        )
    conn.close()


def get_recent_winners(limit: int = 10) -> list[sqlite3.Row]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM winners ORDER BY won_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


def reset_winner_timer(wallet: str) -> None:
    """Legacy — kept so old imports don't break. No longer used in shift logic."""
    pass
