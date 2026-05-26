# SolWatch Bot — Setup & Run Guide

Airdrop bot for the $SOLWATCH pump.fun memecoin mechanic.

---

## Prerequisites

- Python 3.11+ (`python --version`)
- A Solana wallet (Phantom is easiest)
- Helius free RPC key
- Your $SOLWATCH coin deployed on pump.fun

---

## Step 1 — Get a Helius API key (free)

1. Go to https://dev.helius.xyz/dashboard/app
2. Sign up / log in
3. Click "New App" → choose a name → select **Mainnet**
4. Copy the API key shown on the app page
5. Your RPC URL will be: `https://mainnet.helius-rpc.com/?api-key=YOUR_KEY`

---

## Step 2 — Export your deploy wallet private key

This is the wallet you'll use to send prize SOL. It should be the same wallet
you used to deploy the coin on pump.fun (so creator rewards go here).

**Option A — Phantom wallet**
1. Open Phantom → Settings (gear icon) → Security & Privacy → Export Private Key
2. Enter your password
3. You'll get a 64-byte array like `[12,34,56,...]`
4. Convert to base58 using one of:
   - https://www.npmjs.com/package/bs58 (run locally)
   - Or use the helper script below

**Convert JSON array → base58 (one-time, offline):**
```python
import json, base58
arr = [12, 34, 56, ...]  # paste your array here
pk_bytes = bytes(arr)
print(base58.b58encode(pk_bytes).decode())
```
Install: `pip install base58`

**Option B — Solana CLI**
```bash
solana-keygen new -o deploy_wallet.json
cat deploy_wallet.json        # gives you the JSON array
# Public key:
solana-keygen pubkey deploy_wallet.json
```

---

## Step 3 — Find your SOLWATCH mint address

After deploying on pump.fun, the URL of your coin page will look like:
```
https://pump.fun/coin/ABC123def456...
```
The address after `/coin/` is your **mint address**. Copy it.

If you're still pre-launch, set `SOLWATCH_MINT_ADDRESS=set_after_coin_deploy`
and update it after deploying.

---

## Step 4 — Configure environment

```bash
cd solwatch_bot
cp .env.example .env
```

Edit `.env` and fill in all values. Example:
```
DEPLOY_WALLET_PRIVATE_KEY=5Kb8kL...
DEPLOY_WALLET_PUBLIC_KEY=9xKp...
SOLWATCH_MINT_ADDRESS=ABC123def456...
HELIUS_RPC_URL=https://mainnet.helius-rpc.com/?api-key=abc123...
MAGIC_PHRASE=i need a watch
PRIZE_THRESHOLD_USD=200
```

---

## Step 5 — Install dependencies

```bash
pip install -r requirements.txt
```

If you're on Windows and get a build error for `solders`, install the
pre-built wheel:
```bash
pip install solders --prefer-binary
```

---

## Step 6 — Test on devnet first (recommended)

1. Open `pumpfun_scraper.py` and set `USE_MOCK_DATA = True`
2. Edit `MOCK_CALLOUTS` with devnet wallet addresses you control
3. In `.env`, set `SOLANA_NETWORK=devnet` and use a devnet Helius URL
4. Run `python main.py` and watch logs
5. Verify:
   - Mock callouts appear in DB
   - Holder balances update
   - Scores compute
   - Reward counter increments when you send SOL to the deploy wallet
   - Draw fires when counter_usd reaches $200
6. Set `USE_MOCK_DATA = False` and `SOLANA_NETWORK=mainnet-beta` when done

---

## Step 7 — Run the bot (mainnet)

```bash
python main.py
```

Expected startup output:
```
2025-05-12 18:00:00 [INFO] solwatch — SolWatch Bot starting up
2025-05-12 18:00:00 [INFO] solwatch — Mint: ABC123...
2025-05-12 18:00:00 [INFO] solwatch — Deploy wallet: 9xKp...
2025-05-12 18:00:00 [INFO] solwatch — API server starting on http://localhost:8000
```

The bot logs to both stdout and `solwatch_bot.log`.

---

## Step 8 — Wire the frontend

1. Open your `solwatch_demo.html`
2. Remove the hardcoded data + fake setInterval code
3. Paste the contents of `frontend_patch.js` into a `<script>` tag just before `</body>`
4. Check the **ELEMENT ID MAP** comments at the top of `frontend_patch.js` and update the IDs to match your HTML elements

Open the HTML file in your browser — it will fetch live data from `http://localhost:8000/api/state` every 5 seconds.

---

## Creator rewards — fully automatic

The bot auto-collects pump.fun creator fees every **5 seconds** using the
`collect_creator_fee` on-chain instruction. No manual action needed.

How it works:
1. Every 5s the bot **simulates** the collect transaction first (zero SOL cost)
2. If simulation says fees are available → broadcasts the real transaction
3. On success → immediately updates the prize counter (no waiting for the 60s poll)
4. If vault is empty → skips silently (no wasted tx fees)

**To check vault balance manually** (second terminal while bot is running):
```bash
python -c "import asyncio; from pumpfun_collector import print_vault_info; asyncio.run(print_vault_info())"
```

---

## Manual overrides

Force a draw immediately (run in a second terminal):
```bash
python -c "
import asyncio
from draw import check_and_execute_draw
asyncio.run(check_and_execute_draw())
"
```

Skip a draw cycle (temporarily set threshold high):
Edit `PRIZE_THRESHOLD_USD=999999` in `.env` and restart.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `EnvironmentError: Missing SOLWATCH_MINT_ADDRESS` | Set it in `.env` after deploying |
| `RPC error: 429 Too Many Requests` | You're over Helius free tier — add a 0.2s sleep between calls in `holder_tracker.py` |
| `SOL transfer failed: insufficient funds` | Collect fees on pump.fun to fund the deploy wallet |
| Callouts not appearing | Check if pump.fun API changed — inspect Network tab on pump.fun and update `PUMPFUN_REPLIES_URL_TEMPLATE` in `pumpfun_scraper.py` |
| Frontend shows "bot offline" | Bot isn't running, or CORS issue — check that bot is running on port 8000 |
| Winners list is empty | No draws have fired yet (prize counter hasn't reached $200) |

---

## File overview

```
solwatch_bot/
├── main.py               Entry point — starts all loops + API server
├── config.py             All settings from .env
├── db.py                 SQLite schema + all DB helpers
├── solana_client.py      Solana RPC reads + SOL transfers (solders)
├── pumpfun_scraper.py    pump.fun callouts scraper (with mock fallback)
├── holder_tracker.py     Token balance polling + buy/sell detection
├── score_calculator.py   Weighted score formula
├── reward_tracker.py     Deploy wallet watcher + prize counter
├── draw.py               Weighted random draw + payout
├── api.py                FastAPI GET /api/state
├── frontend_patch.js     Drop-in JS for solwatch_demo.html
├── .env.example          Environment variable template
└── requirements.txt      Python dependencies
```

---

## Kill switch

**Ctrl+C** — graceful shutdown. All state is in `solwatch.db` and survives restarts.

The prize counter and all holder states persist across restarts — no lost progress.
