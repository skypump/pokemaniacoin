"""
test_pumpdev_ws.py — Preizkusi pumpdev.io WebSocket za callouts.
Uporaba: py -3.12 test_pumpdev_ws.py
Ctrl+C za stop.
"""
import asyncio
import json
from dotenv import load_dotenv
load_dotenv()

import websockets
from config import settings

MINT = settings.SOLWATCH_MINT_ADDRESS
WS_URL = "wss://pumpdev.io/ws"

# Poskusimo vse znane subscription metode
SUBSCRIPTIONS = [
    {"method": "subscribeNewToken"},
    {"method": "subscribeCallout"},
    {"method": "subscribeCallouts"},
    {"method": "subscribeReply"},
    {"method": "subscribeReplies"},
    {"method": "subscribeTrades", "keys": [MINT]},
    {"method": "subscribeTokenTrade", "keys": [MINT]},
    {"method": "subscribeCallout", "keys": [MINT]},
]


async def main():
    print(f"Mint: {MINT}")
    print(f"WS:   {WS_URL}")
    print("Connecting...\n")

    try:
        async with websockets.connect(WS_URL, ping_interval=20) as ws:
            print("Povezan! Pošljem subscriptions...\n")

            for sub in SUBSCRIPTIONS:
                await ws.send(json.dumps(sub))
                print(f"  → SUB: {sub}")
                await asyncio.sleep(0.1)

            print("\nPoslušam (60s)...\n" + "-" * 60)

            async for raw in ws:
                try:
                    data = json.loads(raw)
                    print(f"MSG: {json.dumps(data, indent=2)[:600]}")
                    print("-" * 40)
                except Exception:
                    print(f"RAW: {raw[:300]}")

    except Exception as e:
        print(f"Napaka: {e}")


asyncio.run(main())
