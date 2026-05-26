"""
test_callout_api.py — Proba vse znane pump.fun endpoints za callouts.
Uporaba: py -3.12 test_callout_api.py
"""
import asyncio
import json
from dotenv import load_dotenv
load_dotenv()

import httpx
from config import settings

MINT = settings.SOLWATCH_MINT_ADDRESS

ENDPOINTS = [
    f"https://frontend-api-v3.pump.fun/replies/{MINT}?limit=10&offset=0",
    f"https://frontend-api-v3.pump.fun/callouts/{MINT}?limit=10&offset=0",
    f"https://frontend-api-v3.pump.fun/calls/{MINT}?limit=10&offset=0",
    f"https://frontend-api.pump.fun/replies/{MINT}?limit=10&offset=0",
    f"https://frontend-api.pump.fun/callouts/{MINT}?limit=10&offset=0",
    f"https://frontend-api.pump.fun/calls/{MINT}?limit=10&offset=0",
    f"https://client-api.pump.fun/replies/{MINT}?limit=10",
    f"https://client-api.pump.fun/callouts/{MINT}?limit=10",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Origin": "https://pump.fun",
    "Referer": f"https://pump.fun/coin/{MINT}",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


async def main():
    print(f"Mint: {MINT}\n")
    async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as client:
        for url in ENDPOINTS:
            try:
                resp = await client.get(url)
                marker = "✅" if resp.status_code == 200 else "❌"
                print(f"{marker} {resp.status_code}  {url}")
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        print(f"     → {type(data).__name__}, preview: {json.dumps(data)[:200]}")
                    except Exception:
                        print(f"     → body: {resp.text[:200]}")
            except Exception as e:
                print(f"💥 ERROR  {url}  → {e}")

asyncio.run(main())
