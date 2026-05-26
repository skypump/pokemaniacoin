"""
add_callout.py — Ročno dodaj callout v bazo (za testiranje ko pump.fun API ne dela).
Uporaba: python add_callout.py <wallet_address>
"""
import sys
import time
from dotenv import load_dotenv
load_dotenv()

from db import init_db, upsert_callout
from config import settings

if len(sys.argv) < 2:
    print("Uporaba: python add_callout.py <wallet_address>")
    sys.exit(1)

wallet = sys.argv[1].strip()
text = settings.MAGIC_PHRASE  # "i need a watch"

init_db()
upsert_callout(wallet, text, int(time.time()), has_magic=True)
print(f"Callout dodan: {wallet}")
print(f'Text: "{text}"')
print("Odpri spletno stran — wallet bo viden v callouts feedu.")
