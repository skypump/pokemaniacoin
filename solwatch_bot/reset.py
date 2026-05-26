"""
reset.py — Počisti bazo in resetiraj mint za novi launch.
Uporaba: py -3.12 reset.py
"""
from dotenv import load_dotenv
load_dotenv()

from db import init_db, get_conn
from pumpfun_collector import get_creator_vault_balance_lamports
import asyncio, re
from pathlib import Path

def reset_db():
    init_db()
    conn = get_conn()
    conn.execute("DELETE FROM callouts")
    conn.execute("DELETE FROM holders")
    conn.execute("DELETE FROM winners")
    conn.execute("DELETE FROM bot_state")
    conn.commit()
    conn.close()
    print("✅ Baza počiščena")

def reset_mint():
    env = Path(".env")
    content = env.read_text(encoding="utf-8")
    current = re.search(r"^SOLWATCH_MINT_ADDRESS=(.+)$", content, re.MULTILINE)
    print(f"   Stari mint: {current.group(1) if current else '?'}")
    new_content = re.sub(
        r"^SOLWATCH_MINT_ADDRESS=.*$",
        "SOLWATCH_MINT_ADDRESS=set_after_coin_deploy",
        content, flags=re.MULTILINE
    )
    env.write_text(new_content, encoding="utf-8")
    print("✅ Mint resetiran → set_after_coin_deploy")

async def show_vault():
    balance = await get_creator_vault_balance_lamports()
    print(f"   Creator vault: {balance / 1e9:.6f} SOL ({balance} lamports)")

print("=" * 50)
print("SOLWATCH BOT RESET")
print("=" * 50)
reset_db()
reset_mint()
print("\nStanje vaulta:")
asyncio.run(show_vault())
print("\n✅ Reset končan — zaženi: py -3.12 main.py")
print("=" * 50)
