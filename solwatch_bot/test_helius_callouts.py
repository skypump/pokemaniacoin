"""
test_helius_callouts.py — Preizkusi ali Helius vidi callout transakcije za naš mint.
Uporaba: py -3.12 test_helius_callouts.py
"""
import asyncio
import json
from dotenv import load_dotenv
load_dotenv()

import httpx
from config import settings

MINT = settings.SOLWATCH_MINT_ADDRESS
API_KEY = settings.HELIUS_RPC_URL.split("api-key=")[-1]

async def main():
    print(f"Mint:    {MINT}")
    print(f"API key: {API_KEY[:8]}...\n")

    async with httpx.AsyncClient(timeout=20) as client:

        # 1. Enhanced parsed transactions za mint address
        print("=== Helius Enhanced Transactions za MINT ===")
        url = f"https://api.helius.xyz/v0/addresses/{MINT}/transactions"
        resp = await client.get(url, params={
            "api-key": API_KEY,
            "limit": 20,
        })
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            txs = resp.json()
            print(f"Število transakcij: {len(txs)}")
            for tx in txs[:5]:
                tx_type = tx.get("type", "?")
                desc = tx.get("description", "")
                source = tx.get("source", "")
                print(f"  type={tx_type} source={source}")
                print(f"  desc={desc[:120]}")
                print()
        else:
            print(resp.text[:300])

        # 2. Poišči s tipom CALLOUT
        print("\n=== Filtriraj po tipu CALLOUT / CALL ===")
        for tx_type in ["CALLOUT", "CALL", "REPLY", "COMMENT"]:
            url2 = f"https://api.helius.xyz/v0/addresses/{MINT}/transactions"
            r = await client.get(url2, params={
                "api-key": API_KEY,
                "limit": 50,
                "type": tx_type,
            })
            data = r.json() if r.status_code == 200 else []
            count = len(data) if isinstance(data, list) else 0
            print(f"  type={tx_type}: {count} rezultatov (status {r.status_code})")
            if count > 0:
                print(f"    → {json.dumps(data[0])[:300]}")

        # 3. Preveri Helius webhook tipi - kaj podpirajo za pump.fun
        print("\n=== Helius /v1/transaction-types ===")
        r3 = await client.get(
            "https://api.helius.xyz/v1/transaction-types",
            params={"api-key": API_KEY}
        )
        if r3.status_code == 200:
            types = r3.json()
            callout_types = [t for t in types if "call" in t.lower() or "reply" in t.lower()]
            print(f"Callout-related tipi: {callout_types}")
            print(f"Vsi tipi ({len(types)}): {types[:30]}")
        else:
            print(f"Status: {r3.status_code} — {r3.text[:200]}")

asyncio.run(main())
