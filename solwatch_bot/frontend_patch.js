/**
 * frontend_patch.js — Drop-in replacement for hardcoded data in solwatch_demo.html
 *
 * INSTRUCTIONS:
 *   1. Find the <script> block in solwatch_demo.html that contains fake data / setInterval
 *   2. Replace it entirely with this block (or paste it just before </body>)
 *   3. Make sure the element IDs match the ones in your HTML (see ELEMENT ID MAP below)
 *
 * ELEMENT ID MAP — update these if your HTML uses different IDs:
 *
 *   #accumulated-usd       → "$147.23" text
 *   #target-usd            → "$200" text
 *   #progress-bar          → <div> whose width% is the progress
 *   #progress-pct          → "73.6%" text
 *   #watches-given         → "3" counter
 *   #total-distributed     → "$600" text
 *   #sol-price             → "$95.42" text
 *   #eligible-list         → <ul> or <div> for eligible holders
 *   #disqualified-list     → <ul> or <div> for disqualified wallets
 *   #winners-list          → <ul> or <div> for recent winners
 */

const API_URL = "http://localhost:8000/api/state";
const POLL_INTERVAL_MS = 5000;

// ── Helpers ───────────────────────────────────────────────────────────────────

function shortWallet(wallet) {
  if (!wallet || wallet.length < 10) return wallet;
  return wallet.slice(0, 4) + "..." + wallet.slice(-4);
}

function formatTime(unixTs) {
  if (!unixTs) return "—";
  const d = new Date(unixTs * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setWidth(id, pct) {
  const el = document.getElementById(id);
  if (el) el.style.width = Math.min(pct, 100) + "%";
}

// ── Renderers ─────────────────────────────────────────────────────────────────

function renderEligible(holders) {
  const container = document.getElementById("eligible-list");
  if (!container) return;

  if (!holders || holders.length === 0) {
    container.innerHTML = '<li class="empty">No eligible holders yet — be first to callout "i need a watch"</li>';
    return;
  }

  container.innerHTML = holders
    .slice(0, 10)   // show top 10 by score (already sorted server-side)
    .map(
      (h, i) => `
      <li class="holder-row eligible">
        <span class="rank">#${i + 1}</span>
        <span class="wallet" title="${h.wallet}">${shortWallet(h.wallet)}</span>
        <span class="callout">"${h.callout_text}"</span>
        <span class="hold">${h.hold_minutes}m</span>
        <span class="chance">${h.chance_pct}%</span>
      </li>`
    )
    .join("");
}

function renderDisqualified(disq) {
  const container = document.getElementById("disqualified-list");
  if (!container) return;

  if (!disq || disq.length === 0) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = disq
    .slice(0, 5)
    .map(
      (d) => `
      <li class="holder-row disqualified">
        <span class="wallet" title="${d.wallet}">${shortWallet(d.wallet)}</span>
        <span class="callout">"${d.callout_text}"</span>
        <span class="badge sold">SOLD</span>
        <span class="time">${formatTime(d.sold_at)}</span>
      </li>`
    )
    .join("");
}

function renderWinners(winners) {
  const container = document.getElementById("winners-list");
  if (!container) return;

  if (!winners || winners.length === 0) {
    container.innerHTML = '<li class="empty">No winners yet — first draw coming soon</li>';
    return;
  }

  container.innerHTML = winners
    .map(
      (w) => `
      <li class="winner-row">
        <span class="wallet" title="${w.wallet}">${shortWallet(w.wallet)}</span>
        <span class="amount">${w.amount_sol.toFixed(4)} SOL</span>
        <span class="usd">($${w.amount_usd.toFixed(2)})</span>
        <span class="time">${formatTime(w.won_at)}</span>
        <a class="tx-link"
           href="https://solscan.io/tx/${w.tx_hash}"
           target="_blank"
           rel="noopener">↗</a>
      </li>`
    )
    .join("");
}

// ── Main update function ───────────────────────────────────────────────────────

async function updateDashboard() {
  let data;
  try {
    const resp = await fetch(API_URL);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    data = await resp.json();
  } catch (err) {
    console.warn("SolWatch API unreachable:", err.message);
    // Show a subtle "offline" indicator without crashing the UI
    const el = document.getElementById("sol-price");
    if (el) el.textContent = "bot offline";
    return;
  }

  // ── Counter + progress ──────────────────────────────────────────────────────
  setText("accumulated-usd", `$${data.accumulated_usd.toFixed(2)}`);
  setText("target-usd", `$${data.target_usd.toFixed(0)}`);
  setText("progress-pct", `${data.progress_pct.toFixed(1)}%`);
  setWidth("progress-bar", data.progress_pct);

  // ── Stats ───────────────────────────────────────────────────────────────────
  setText("watches-given", data.watches_given);
  setText("total-distributed", `$${data.total_distributed_usd.toFixed(2)}`);
  setText("sol-price", `$${data.sol_price_usd.toFixed(2)}`);

  // ── Lists ───────────────────────────────────────────────────────────────────
  renderEligible(data.eligible_holders);
  renderDisqualified(data.disqualified);
  renderWinners(data.recent_winners);
}

// ── Boot ───────────────────────────────────────────────────────────────────────

updateDashboard();  // immediate first fetch
setInterval(updateDashboard, POLL_INTERVAL_MS);
