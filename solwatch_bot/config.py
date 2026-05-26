"""
config.py — loads all settings from .env file.
"""
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Settings:
    # ── Wallet ────────────────────────────────────────────────────────────────
    DEPLOY_WALLET_PRIVATE_KEY: str = os.getenv("DEPLOY_WALLET_PRIVATE_KEY", "")
    DEPLOY_WALLET_PUBLIC_KEY: str = os.getenv("DEPLOY_WALLET_PUBLIC_KEY", "")
    SOLWATCH_MINT_ADDRESS: str = os.getenv("SOLWATCH_MINT_ADDRESS", "")

    # ── RPC ───────────────────────────────────────────────────────────────────
    HELIUS_RPC_URL: str = os.getenv("HELIUS_RPC_URL", "")
    SOLANA_NETWORK: str = os.getenv("SOLANA_NETWORK", "mainnet-beta")

    # ── Mechanic ──────────────────────────────────────────────────────────────
    MAGIC_PHRASE: str = os.getenv("MAGIC_PHRASE", "i choose you").lower()

    # Shift = 10-minute payout cycle
    SHIFT_INTERVAL_SECONDS: int = int(os.getenv("SHIFT_INTERVAL_SECONDS", "600"))

    # 80% of collected creator fees go to shift vault, 20% to ops
    SHIFT_VAULT_FRACTION: float = float(os.getenv("SHIFT_VAULT_FRACTION", "0.70"))

    # Minimum token balance to participate in shifts
    MIN_HOLDER_BALANCE: int = int(os.getenv("MIN_HOLDER_BALANCE", "100000"))

    # ── Pokemon evolution thresholds (hold time in seconds → level 1-5) ─────────
    # Each tier multiplies score; callout_verified adds ×2 on top
    EVOLUTION_THRESHOLDS: list[int] = [
        0,     # Level 1 — 0 min
        900,   # Level 2 — 15 min
        1800,  # Level 3 — 30 min
        2700,  # Level 4 — 45 min
        3600,  # Level 5 — 60 min (Mega)
    ]

    # ── Pokemon names (1=Fire, 2=Water, 3=Grass) ─────────────────────────────
    POKEMON_NAMES: list[str] = ["Embyr", "Tidalin", "Sproutly"]
    POKEMON_TYPES: list[str] = ["fire", "water", "grass"]

    # ── Score formula ─────────────────────────────────────────────────────────
    # score = balance × seconds_held × evolution_level × (2 if callout_verified)
    CLICK_WEIGHT: int = int(os.getenv("CLICK_WEIGHT", "1000"))  # kept for compat

    # ── Price cache ───────────────────────────────────────────────────────────
    SOL_PRICE_CACHE_SECONDS: int = int(os.getenv("SOL_PRICE_CACHE_SECONDS", "60"))

    # ── External APIs ─────────────────────────────────────────────────────────
    PUMPFUN_API_BASE: str = "https://frontend-api-v3.pump.fun"
    COINGECKO_PRICE_URL: str = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=solana&vs_currencies=usd"
    )

    # ── Poll intervals (seconds) ───────────────────────────────────────────────
    CALLOUT_POLL_INTERVAL: float = 0.7
    HOLDER_POLL_INTERVAL: float = 3.0
    SCORE_CALC_INTERVAL: float = 0.7
    REWARD_POLL_INTERVAL: float = 0.7
    DRAW_CHECK_INTERVAL: float = 0.7

    # ── HTTP timeouts ─────────────────────────────────────────────────────────
    HTTP_TIMEOUT: float = 15.0

    # ── Transaction retry ─────────────────────────────────────────────────────
    TX_RETRY_COUNT: int = 3
    TX_RETRY_BASE_DELAY: float = 2.0

    # ── API server ────────────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # ── Safety buffer for tx fees (lamports) ─────────────────────────────────
    TX_FEE_BUFFER_LAMPORTS: int = 10_000  # 0.00001 SOL

    def validate(self) -> None:
        missing = []
        if not self.DEPLOY_WALLET_PRIVATE_KEY:
            missing.append("DEPLOY_WALLET_PRIVATE_KEY")
        if not self.DEPLOY_WALLET_PUBLIC_KEY:
            missing.append("DEPLOY_WALLET_PUBLIC_KEY")
        if not self.HELIUS_RPC_URL:
            missing.append("HELIUS_RPC_URL")
        if not self.SOLWATCH_MINT_ADDRESS or self.SOLWATCH_MINT_ADDRESS == "set_after_coin_deploy":
            missing.append("SOLWATCH_MINT_ADDRESS")
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                "Copy .env.example to .env and fill in the values."
            )

    def is_devnet(self) -> bool:
        return self.SOLANA_NETWORK == "devnet"


settings = Settings()
