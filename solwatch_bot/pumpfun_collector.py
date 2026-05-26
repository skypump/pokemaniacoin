from __future__ import annotations
"""
pumpfun_collector.py — Auto-collect pump.fun creator fees every 5 seconds.

HOW IT WORKS:
  pump.fun accumulates creator fees in a program-derived vault account.
  The vault is per-creator-wallet (not per-coin), so one instruction collects
  fees from ALL your coins simultaneously.

  collect_creator_fees() returns the EXACT lamports pulled from the vault,
  measured as (vault_balance_before - vault_balance_after). This number is
  the only source that feeds the prize counter — dev sells, gifted SOL,
  or any other wallet movement are completely ignored.

  We check vault balance first. If vault is empty we skip entirely (no RPC
  simulation needed). If the vault has a balance we simulate, then send.

INSTRUCTION: collect_creator_fee
  Discriminator: sha256("global:collect_creator_fee")[:8]

ACCOUNTS (in order — order matters for Anchor):
  0. creator          writable, signer     — your deploy wallet
  1. creator_vault    writable             — PDA(["creator-vault", creator_pubkey])
  2. event_authority  readonly             — PDA(["__event_authority"])
  3. system_program   readonly             — 11111...
  4. program          readonly             — pump.fun program ID (self-reference for CPI events)

SOURCE: pump.fun public IDL at github.com/pump-fun/pump-public-docs
"""
import asyncio
import base64
import hashlib
import logging
import time

from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction

from config import settings
from solana_client import _rpc, get_latest_blockhash

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

PUMP_PROGRAM_ID = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
SYSTEM_PROGRAM_ID = Pubkey.from_string("11111111111111111111111111111111")

# Instruction discriminator: sha256("global:collect_creator_fee")[:8]
# Computed at import time from the Anchor convention — no hard-coded magic bytes.
COLLECT_DISCRIMINATOR: bytes = hashlib.sha256(
    b"global:collect_creator_fee"
).digest()[:8]


# ── PDA derivation ────────────────────────────────────────────────────────────

def get_creator_vault_pda(creator_pubkey: Pubkey) -> Pubkey:
    """
    The vault where pump.fun accumulates creator fees.
    Seeds: ["creator-vault", creator_pubkey_bytes]
    One vault per creator wallet — aggregates fees from ALL your coins.
    """
    pda, _bump = Pubkey.find_program_address(
        [b"creator-vault", bytes(creator_pubkey)],
        PUMP_PROGRAM_ID,
    )
    return pda


def get_event_authority_pda() -> Pubkey:
    """Standard Anchor event-authority PDA used for CPI event emission."""
    pda, _bump = Pubkey.find_program_address(
        [b"__event_authority"],
        PUMP_PROGRAM_ID,
    )
    return pda


# ── Cached keypair (avoid re-parsing base58 on every call) ───────────────────

_creator_keypair: Keypair | None = None


def _get_creator() -> Keypair:
    global _creator_keypair
    if _creator_keypair is None:
        _creator_keypair = Keypair.from_base58_string(settings.DEPLOY_WALLET_PRIVATE_KEY)
    return _creator_keypair


# ── Transaction builder ───────────────────────────────────────────────────────

async def _build_collect_tx() -> str:
    """
    Build and sign a collect_creator_fee transaction.
    Returns the base64-encoded transaction ready to send or simulate.
    Fetches a fresh blockhash each time (call just before send/simulate).
    """
    creator = _get_creator()
    creator_vault = get_creator_vault_pda(creator.pubkey())
    event_authority = get_event_authority_pda()

    ix = Instruction(
        program_id=PUMP_PROGRAM_ID,
        accounts=[
            AccountMeta(creator.pubkey(),    is_signer=True,  is_writable=True),
            AccountMeta(creator_vault,        is_signer=False, is_writable=True),
            AccountMeta(SYSTEM_PROGRAM_ID,    is_signer=False, is_writable=False),
            AccountMeta(event_authority,      is_signer=False, is_writable=False),
            AccountMeta(PUMP_PROGRAM_ID,      is_signer=False, is_writable=False),
        ],
        data=COLLECT_DISCRIMINATOR,
    )

    blockhash = await get_latest_blockhash()
    tx = Transaction.new_signed_with_payer(
        instructions=[ix],
        payer=creator.pubkey(),
        signing_keypairs=[creator],
        recent_blockhash=blockhash,
    )
    return base64.b64encode(bytes(tx)).decode()


# ── Core collect logic ────────────────────────────────────────────────────────

async def collect_creator_fees() -> int:
    """
    Try to collect any accumulated pump.fun creator fees.

    Returns the exact lamports collected from the creator vault (vault balance
    before minus vault balance after). Returns 0 if nothing was collected.

    This is the ONLY function that should feed the prize counter — the vault
    delta cannot be confused with dev sells or other wallet movements.
    """
    try:
        # ── Step 1: Check vault balance — skip everything if empty ────────────
        vault_before = await get_creator_vault_balance_lamports()
        if vault_before == 0:
            logger.debug("Creator vault is empty — skipping collect")
            return 0

        logger.debug("Creator vault has %.9f SOL — attempting collect", vault_before / 1e9)

        # ── Step 2: Simulate (confirm instruction will succeed) ───────────────
        sim_tx_b64 = await _build_collect_tx()
        sim_result = await _rpc(
            "simulateTransaction",
            [sim_tx_b64, {"encoding": "base64", "commitment": "confirmed"}],
        )
        err = sim_result["result"]["value"].get("err")
        if err:
            logger.debug("Collect simulation failed: %s", err)
            return 0

        # ── Step 3: Send real transaction (fresh tx = fresh blockhash) ────────
        send_tx_b64 = await _build_collect_tx()
        send_result = await _rpc(
            "sendTransaction",
            [send_tx_b64, {"encoding": "base64", "preflightCommitment": "confirmed"}],
        )
        sig: str = send_result["result"]

        # ── Step 4: Wait for confirmation, then measure exact amount ──────────
        # Small wait so the balance reflects the confirmed tx.
        await asyncio.sleep(3)
        vault_after = await get_creator_vault_balance_lamports()

        collected = max(0, vault_before - vault_after)
        if collected > 0:
            logger.info(
                "Creator fees collected: %.9f SOL (%d lamports) — tx: %s",
                collected / 1e9, collected, sig,
            )
        else:
            # Tx landed but vault didn't decrease — log for debugging
            logger.warning(
                "Collect tx sent (%s) but vault balance unchanged (before=%d after=%d)",
                sig, vault_before, vault_after,
            )

        return collected

    except Exception as exc:
        logger.error("collect_creator_fees error: %s", exc)
        return 0


# ── Diagnostic helper ─────────────────────────────────────────────────────────

async def get_creator_vault_balance_lamports() -> int:
    """
    Return how many lamports are sitting in the creator vault.
    Useful for debugging. Returns 0 if account doesn't exist yet.
    """
    creator = _get_creator()
    vault = get_creator_vault_pda(creator.pubkey())
    try:
        data = await _rpc("getBalance", [str(vault), {"commitment": "confirmed"}])
        return int(data["result"]["value"])
    except Exception:
        return 0


async def print_vault_info() -> None:
    """CLI helper: print vault address and current balance."""
    creator = _get_creator()
    vault = get_creator_vault_pda(creator.pubkey())
    event_auth = get_event_authority_pda()
    balance = await get_creator_vault_balance_lamports()
    print(f"Creator:         {creator.pubkey()}")
    print(f"Creator vault:   {vault}")
    print(f"Event authority: {event_auth}")
    print(f"Vault balance:   {balance / 1e9:.9f} SOL ({balance} lamports)")
    print(f"Collect discrim: {list(COLLECT_DISCRIMINATOR)}")
