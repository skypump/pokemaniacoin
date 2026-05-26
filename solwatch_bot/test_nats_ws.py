"""
test_nats_ws.py — Poslušaj pump.fun NATS WebSocket in izpiši vse subjects za naš mint.
Uporaba: py -3.12 test_nats_ws.py
Ctrl+C za stop.

Namesti: py -3.12 -m pip install websockets
"""
import asyncio
import json
from dotenv import load_dotenv
load_dotenv()

import websockets
from config import settings

MINT = settings.SOLWATCH_MINT_ADDRESS
NATS_URL = "wss://unified-prod.nats.realtime.pump.fun"

# Poskusimo te subjects — wildcard > = vse, ostali so specifični za naš mint
SUBJECTS_TO_TRY = [
    f"unifiedCalloutEvent.processed.{MINT}",
    f"unifiedReplyEvent.processed.{MINT}",
    f"callout.{MINT}",
    f"reply.{MINT}",
    f"unifiedTradeEvent.processed.{MINT}",  # ta vemo da dela
    ">",  # wildcard = VSE (bo preveč, samo za test)
]


def encode(msg: str) -> bytes:
    return (msg + "\r\n").encode()


async def main():
    print(f"Mint:  {MINT}")
    print(f"NATS:  {NATS_URL}")
    print("Connecting...\n")

    try:
        async with websockets.connect(
            NATS_URL,
            additional_headers={
                "Origin": "https://pump.fun",
                "User-Agent": "Mozilla/5.0",
            },
            ping_interval=20,
        ) as ws:
            # 1. Preberi INFO
            info_raw = await ws.recv()
            info_str = info_raw if isinstance(info_raw, str) else info_raw.decode(errors="replace")
            print(f"SERVER INFO: {info_str[:200]}\n")

            # 2. CONNECT
            connect_msg = json.dumps({
                "verbose": False,
                "pedantic": False,
                "lang": "python",
                "version": "1.0.0",
                "protocol": 1,
            })
            await ws.send(encode(f"CONNECT {connect_msg}"))
            await asyncio.sleep(0.3)

            # 3. Subscribeamo na subjects (preskoči wildcard za zdaj)
            sid = 1
            for subj in SUBJECTS_TO_TRY[:-1]:  # brez wildcard >
                await ws.send(encode(f"SUB {subj} {sid}"))
                print(f"SUB [{sid}] {subj}")
                sid += 1

            print("\nPoslušam... (Ctrl+C za stop)\n" + "-" * 60)

            # 4. Prejemaj sporočila
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                    msg = raw if isinstance(raw, str) else raw.decode(errors="replace")

                    if msg.startswith("PING"):
                        await ws.send(encode("PONG"))
                        continue
                    if msg.strip() in ("+OK", ""):
                        continue

                    print(f"MSG: {msg[:500]}")
                    print("-" * 40)

                except asyncio.TimeoutError:
                    print("(30s brez sporočila — pošljem PING)")
                    await ws.send(encode("PING"))

    except Exception as e:
        print(f"Napaka: {e}")


asyncio.run(main())
