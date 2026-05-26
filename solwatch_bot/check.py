"""
check.py — Preveri vse komponente preden greš live.
Zaženi z: python check.py
"""
import asyncio
import os
import sys
import httpx
from dotenv import load_dotenv

load_dotenv()

OK  = "  [OK] "
FAIL = "  [FAIL] "
WARN = "  [WARN] "

errors = 0

def ok(msg):   print(OK + msg)
def fail(msg): print(FAIL + msg); global errors; errors += 1
def warn(msg): print(WARN + msg)

# ── 1. .env values ────────────────────────────────────────────────
print("\n--- 1. .env ---")

priv = os.getenv("DEPLOY_WALLET_PRIVATE_KEY", "")
pub  = os.getenv("DEPLOY_WALLET_PUBLIC_KEY", "")
mint = os.getenv("SOLWATCH_MINT_ADDRESS", "")
rpc  = os.getenv("HELIUS_RPC_URL", "")

if priv and priv != "your_base58_private_key_here" and len(priv) > 30:
    ok("DEPLOY_WALLET_PRIVATE_KEY set")
else:
    fail("DEPLOY_WALLET_PRIVATE_KEY missing — export from Phantom")

if pub and pub != "your_public_key_here" and len(pub) > 30:
    ok(f"DEPLOY_WALLET_PUBLIC_KEY: {pub[:8]}...{pub[-4:]}")
else:
    fail("DEPLOY_WALLET_PUBLIC_KEY missing")

if rpc and "helius" in rpc and "api-key" in rpc:
    ok("HELIUS_RPC_URL set")
else:
    fail("HELIUS_RPC_URL missing or invalid")

if mint and mint != "set_after_coin_deploy" and len(mint) > 20:
    ok(f"SOLWATCH_MINT_ADDRESS: {mint[:8]}...{mint[-4:]}")
else:
    warn("SOLWATCH_MINT_ADDRESS not set yet — bot will auto-detect at launch")

# ── 2. Python packages ────────────────────────────────────────────
print("\n--- 2. Python packages ---")

packages = ["httpx", "fastapi", "uvicorn", "dotenv", "solders"]
for pkg in packages:
    try:
        __import__(pkg if pkg != "dotenv" else "dotenv")
        ok(pkg)
    except ImportError:
        fail(f"{pkg} not installed — run: pip install -r requirements.txt")

# ── 3. Helius RPC ─────────────────────────────────────────────────
print("\n--- 3. Helius RPC connection ---")

async def check_helius():
    if not rpc:
        fail("Skipping — no RPC URL")
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(rpc, json={"jsonrpc":"2.0","id":1,"method":"getHealth"})
            if r.status_code == 200 and r.json().get("result") == "ok":
                ok("Helius RPC reachable and healthy")
            else:
                fail(f"Helius returned unexpected response: {r.status_code}")
    except Exception as e:
        fail(f"Cannot reach Helius: {e}")

asyncio.run(check_helius())

# ── 4. Deploy wallet balance ──────────────────────────────────────
print("\n--- 4. Deploy wallet SOL balance ---")

async def check_wallet():
    if not rpc or not pub or pub == "your_public_key_here":
        warn("Skipping — wallet not configured")
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(rpc, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "getBalance",
                "params": [pub]
            })
            lamports = r.json()["result"]["value"]
            sol = lamports / 1e9
            if sol >= 0.05:
                ok(f"Deploy wallet balance: {sol:.4f} SOL")
            elif sol > 0:
                warn(f"Deploy wallet balance low: {sol:.4f} SOL — needs at least 0.05 SOL for tx fees")
            else:
                fail("Deploy wallet is empty — send some SOL for transaction fees")
    except Exception as e:
        fail(f"Could not check wallet balance: {e}")

asyncio.run(check_wallet())

# ── 5. pump.fun API ───────────────────────────────────────────────
print("\n--- 5. pump.fun API ---")

async def check_pumpfun():
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get("https://frontend-api.pump.fun/coins?offset=0&limit=1&sort=created_timestamp&order=DESC")
            if r.status_code == 200:
                ok("pump.fun API reachable")
            else:
                warn(f"pump.fun returned {r.status_code} — may be rate limiting")
    except Exception as e:
        fail(f"Cannot reach pump.fun: {e}")

asyncio.run(check_pumpfun())

# ── 6. SOL price (CoinGecko) ──────────────────────────────────────
print("\n--- 6. SOL price feed ---")

async def check_price():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd")
            price = r.json()["solana"]["usd"]
            ok(f"SOL price: ${price}")
    except Exception as e:
        fail(f"Cannot fetch SOL price: {e}")

asyncio.run(check_price())

# ── 7. Bot API (only if running) ──────────────────────────────────
print("\n--- 7. Bot API (localhost:8000) ---")

async def check_api():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get("http://localhost:8000/health")
            if r.status_code == 200:
                ok("Bot API is running")
                r2 = await client.get("http://localhost:8000/api/state")
                d = r2.json()
                ok(f"  Prize counter: ${d.get('accumulated_usd', 0):.2f} / ${d.get('target_usd', 200):.0f}")
                ok(f"  Eligible holders: {len(d.get('eligible_holders', []))}")
                ok(f"  Watches given: {d.get('watches_given', 0)}")
            else:
                warn("Bot API returned non-200 — not running yet (normal before launch)")
    except Exception:
        warn("Bot API not running — start with: python main.py")

asyncio.run(check_api())

# ── Result ────────────────────────────────────────────────────────
print("\n" + "="*45)
if errors == 0:
    print("  ALL CHECKS PASSED — ready to launch!")
else:
    print(f"  {errors} issue(s) found — fix before going live")
print("="*45 + "\n")
