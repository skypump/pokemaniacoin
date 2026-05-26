from __future__ import annotations
"""
solana_client.py — All Solana RPC interactions.

Uses raw JSON-RPC over httpx for reads (avoids solana-py version quirks),
and solders for building + signing transactions.

All balance values are in lamports (1 SOL = 1_000_000_000 lamports).
"""
import asyncio
import base64
import logging
import time
from typing import Any

import httpx
from solders.hash import Hash
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction

from config import settings

logger = logging.getLogger(__name__)

_rpc_call_id = 0


async def _rpc(method: str, params: list[Any] | dict[str, Any]) -> Any:
    """Send a single JSON-RPC request to Helius. Returns the full response dict."""
    global _rpc_call_id
    _rpc_call_id += 1
    payload = {
        "jsonrpc": "2.0",
        "id": _rpc_call_id,
        "method": method,
        "params": params,
    }
    async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT) as client:
        resp = await client.post(settings.HELIUS_RPC_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

    if "error" in data:
        raise RuntimeError(f"RPC error [{method}]: {data['error']}")
    return data


async def get_sol_balance_lamports(wallet_pubkey: str) -> int:
    """Return the SOL balance of a wallet in lamports."""
    data = await _rpc("getBalance", [wallet_pubkey, {"commitment": "confirmed"}])
    return int(data["result"]["value"])


async def get_token_balance_raw(wallet_pubkey: str, mint: str) -> int:
    """
    Return the raw token balance (base units, NOT divided by decimals) for
    a specific SPL token mint held by wallet_pubkey.
    Returns 0 if the wallet holds no tokens.
    """
    data = await _rpc(
        "getTokenAccountsByOwner",
        [
            wallet_pubkey,
            {"mint": mint},
            {"encoding": "jsonParsed", "commitment": "confirmed"},
        ],
    )
    accounts = data["result"]["value"]
    if not accounts:
        return 0

    total = 0
    for acc in accounts:
        try:
            amount_str = (
                acc["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"]
            )
            total += int(amount_str)
        except (KeyError, ValueError):
            pass
    return total


async def get_latest_blockhash() -> Hash:
    """Fetch the latest blockhash needed to build a transaction."""
    data = await _rpc("getLatestBlockhash", [{"commitment": "confirmed"}])
    blockhash_str = data["result"]["value"]["blockhash"]
    return Hash.from_string(blockhash_str)


async def confirm_transaction(signature: str, max_wait_seconds: int = 60) -> bool:
    """Poll until transaction is confirmed or timeout. Returns True on success."""
    deadline = time.monotonic() + max_wait_seconds
    while time.monotonic() < deadline:
        await asyncio.sleep(2)
        data = await _rpc("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])
        statuses = data["result"]["value"]
        if statuses and statuses[0]:
            status = statuses[0]
            if status.get("err"):
                logger.error("Transaction %s failed on-chain: %s", signature, status["err"])
                return False
            if status.get("confirmationStatus") in ("confirmed", "finalized"):
                return True
    logger.warning("Transaction %s not confirmed within %ds", signature, max_wait_seconds)
    return False


async def send_sol(to_wallet: str, lamports: int) -> str:
    """
    Transfer `lamports` from the DEPLOY_WALLET to `to_wallet`.
    Returns the transaction signature string.
    Retries up to TX_RETRY_COUNT times with exponential backoff.
    Raises on all retries exhausted.
    """
    sender = Keypair.from_base58_string(settings.DEPLOY_WALLET_PRIVATE_KEY)
    recipient = Pubkey.from_string(to_wallet)

    last_exc: Exception = RuntimeError("No attempts made")
    delay = settings.TX_RETRY_BASE_DELAY

    for attempt in range(1, settings.TX_RETRY_COUNT + 1):
        try:
            blockhash = await get_latest_blockhash()

            ix = transfer(
                TransferParams(
                    from_pubkey=sender.pubkey(),
                    to_pubkey=recipient,
                    lamports=lamports,
                )
            )

            # Build and sign a legacy (non-versioned) transaction
            tx = Transaction.new_signed_with_payer(
                instructions=[ix],
                payer=sender.pubkey(),
                signing_keypairs=[sender],
                recent_blockhash=blockhash,
            )

            # Serialize to base64 for sendTransaction RPC
            tx_bytes = bytes(tx)
            tx_b64 = base64.b64encode(tx_bytes).decode()

            data = await _rpc(
                "sendTransaction",
                [tx_b64, {"encoding": "base64", "preflightCommitment": "confirmed"}],
            )
            sig: str = data["result"]
            logger.info(
                "SOL transfer sent (attempt %d): %s lamports to %s | sig=%s",
                attempt, lamports, to_wallet, sig,
            )

            confirmed = await confirm_transaction(sig)
            if not confirmed:
                raise RuntimeError(f"Transaction {sig} failed confirmation")

            return sig

        except Exception as exc:
            last_exc = exc
            logger.warning(
                "SOL transfer attempt %d/%d failed: %s — retrying in %.1fs",
                attempt, settings.TX_RETRY_COUNT, exc, delay,
            )
            if attempt < settings.TX_RETRY_COUNT:
                await asyncio.sleep(delay)
                delay *= 2  # exponential backoff

    raise RuntimeError(
        f"SOL transfer to {to_wallet} failed after {settings.TX_RETRY_COUNT} attempts: {last_exc}"
    )


async def get_deploy_wallet_sol_balance() -> int:
    """Convenience: return DEPLOY_WALLET SOL balance in lamports."""
    return await get_sol_balance_lamports(settings.DEPLOY_WALLET_PUBLIC_KEY)


async def get_all_token_holders(mint: str) -> dict[str, int]:
    """
    Return all wallets holding `mint` and their raw token balances.
    Uses Helius getTokenAccounts (DAS extension) with page-based pagination.
    Returns {wallet_pubkey: raw_balance}.
    """
    holders: dict[str, int] = {}
    page = 1
    limit = 1000

    while True:
        data = await _rpc(
            "getTokenAccounts",
            {"mint": mint, "limit": limit, "page": page},
        )
        result = data.get("result", {})
        accounts = result.get("token_accounts", [])
        if not accounts:
            break

        for acc in accounts:
            owner = acc.get("owner")
            amount = acc.get("amount", 0)
            if owner and int(amount) > 0:
                holders[owner] = int(amount)

        if len(accounts) < limit:
            break
        page += 1

    return holders


# ── Pump.fun creator fee claiming ─────────────────────────────────────────────
#
# pump.fun stores creator fees in a program-derived account (PDA).
# To receive them you must send a "collectCreatorFee" (or "withdraw") instruction
# to the pump.fun program. Without the verified IDL we can't safely build this
# instruction automatically.
#
# RECOMMENDED WORKFLOW:
#   1. Periodically visit pump.fun → your coin page → click "Collect Fees"
#   2. That SOL lands in your DEPLOY_WALLET
#   3. The bot's poll_creator_rewards() detects the balance increase and credits
#      the prize_counter automatically.
#
# If you want the bot to auto-claim, you need pump.fun's program IDL. The
# program ID is: 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P
# When the IDL is available, implement build_collect_creator_fee_tx() here.
#
# TODO: implement auto-claim when IDL is confirmed

async def check_unclaimed_creator_fees() -> float:
    """
    Placeholder. Returns 0 because we can't query the fee vault without the IDL.
    The real balance increase appears in DEPLOY_WALLET after you manually claim.
    """
    return 0.0
