// ═══════════════════════════════════════════════════════════════
// SolWatch Dashboard — Live API Script
// Zamenjaj celoten <script>...</script> blok na dnu HTML s tem.
// Zahteva: bot teče na http://localhost:8000
// ═══════════════════════════════════════════════════════════════

const API_URL       = 'http://localhost:8000/api/state';
const POLL_MS       = 5000;   // osveži vsakih 5 sekund

// ── Pomožne funkcije ─────────────────────────────────────────────

function shortWallet(wallet) {
  if (!wallet || wallet.length < 8) return wallet || '—';
  return wallet.slice(0, 4) + '...' + wallet.slice(-4);
}

function timeAgo(unixTs) {
  if (!unixTs) return '—';
  const diffMin = Math.floor((Date.now() / 1000 - unixTs) / 60);
  if (diffMin < 1)  return 'ravnokar';
  if (diffMin < 60) return diffMin + 'm nazaj';
  return Math.floor(diffMin / 60) + 'h nazaj';
}

function fmtBalance(n) {
  if (!n) return '0';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return Math.round(n / 1000) + 'k';
  return n.toString();
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function setWidth(id, pct) {
  const el = document.getElementById(id);
  if (el) el.style.width = Math.min(Math.max(pct, 0), 100) + '%';
}

// ── Leaderboard (top 5) ──────────────────────────────────────────

function renderLeaderboard(holders) {
  const el = document.querySelector('.leaderboard');
  if (!el) return;

  if (!holders.length) {
    el.innerHTML = '<div style="padding:24px;text-align:center;color:rgba(255,255,255,0.3)">Še ni primernih holderjev</div>';
    return;
  }

  const rankCls   = ['gold', 'silver', 'bronze', '', ''];
  const badgeCls  = ['rank-1', 'rank-2', 'rank-3', '', ''];

  el.innerHTML = holders.slice(0, 5).map((h, i) => `
    <div class="leader-row ${rankCls[i]}">
      <div class="rank-badge ${badgeCls[i]}">${i + 1}</div>
      <div class="wallet-info">
        <div class="wallet-addr">${shortWallet(h.wallet)}</div>
        <div class="wallet-meta">${fmtBalance(h.balance)} held · kupil ${h.hold_minutes}m nazaj</div>
      </div>
      <div class="score-display">
        <div class="score-num">${Math.round(h.score).toLocaleString()}</div>score
      </div>
      <div class="chance-pill${h.chance_pct >= 20 ? ' high' : ''}">${h.chance_pct.toFixed(1)}%</div>
    </div>
  `).join('');
}

// ── Callouts feed ────────────────────────────────────────────────

function renderCallouts(holders, disqualified) {
  const feed = document.querySelector('.callouts-feed');
  if (!feed) return;

  const total   = holders.length + disqualified.length;
  const eligCnt = holders.length;
  const disqCnt = disqualified.length;

  // Posodobi section meta
  const section = document.getElementById('eligible');
  if (section) {
    const meta = section.querySelector('.section-meta');
    if (meta) meta.textContent =
      `zbrano s pump.fun · ${total} skupaj · ${eligCnt} primernih`;
  }

  // Posodobi tab counts
  document.querySelectorAll('.callout-tab').forEach(tab => {
    const countEl = tab.querySelector('.tab-count');
    if (!countEl) return;
    const f = tab.dataset.filter;
    if (f === 'all')          countEl.textContent = total;
    if (f === 'eligible')     countEl.textContent = eligCnt;
    if (f === 'disqualified') countEl.textContent = disqCnt;
  });

  // Primernih
  const eligRows = holders.map(h => `
    <div class="callout-row eligible" data-filter="all eligible">
      <div class="callout-left">
        <div class="status-badge eligible-badge">✓</div>
        <div class="wallet-block">
          <div class="wallet-addr">${shortWallet(h.wallet)}</div>
          <div class="callout-quote">"${h.callout_text || 'i need a watch'}"</div>
        </div>
      </div>
      <div class="callout-mid">
        <div class="action-tag buy">
          <span class="action-arrow">↑</span> Zadnje: BUY · ${h.hold_minutes}m nazaj
        </div>
        <div class="balance-info">${fmtBalance(h.balance)} SOLWATCH · score ${Math.round(h.score).toLocaleString()}</div>
      </div>
      <div class="callout-right">
        <div class="chance-value${h.chance_pct >= 20 ? ' gold' : ''}">${h.chance_pct.toFixed(1)}%</div>
        <div class="chance-label">možnost</div>
      </div>
    </div>
  `).join('');

  // Diskvalificiranih
  const disqRows = disqualified.map(h => `
    <div class="callout-row disqualified" data-filter="all disqualified">
      <div class="callout-left">
        <div class="status-badge dq-badge">✗</div>
        <div class="wallet-block">
          <div class="wallet-addr disabled">${shortWallet(h.wallet)}</div>
          <div class="callout-quote disabled">"${h.callout_text || 'i need a watch'}"</div>
        </div>
      </div>
      <div class="callout-mid">
        <div class="action-tag sell">
          <span class="action-arrow">↓</span> Zadnje: SELL · ${h.sold_at ? timeAgo(h.sold_at) : '—'}
        </div>
        <div class="balance-info disabled">0 SOLWATCH · score reset</div>
      </div>
      <div class="callout-right">
        <div class="chance-value disabled">0%</div>
        <div class="chance-label dq-reason">${h.reason || 'prodal'}</div>
      </div>
    </div>
  `).join('');

  feed.innerHTML = eligRows + disqRows + (total > 0 ? `
    <button class="show-more-btn" style="cursor:default">
      Skupaj ${total} callout${total !== 1 ? 'ov' : ''} · osvežuje se samodejno
    </button>
  ` : '<div style="padding:24px;text-align:center;color:rgba(255,255,255,0.3)">Še nobenih calloutov</div>');

  // Ponastavi filter na aktivni tab
  const activeTab = document.querySelector('.callout-tab.active');
  if (activeTab) applyFilter(activeTab.dataset.filter);
}

// ── Winners grid ─────────────────────────────────────────────────

function renderWinners(winners, totalGiven) {
  const grid = document.querySelector('.winners-grid');
  if (!grid) return;

  if (!winners.length) {
    grid.innerHTML = `
      <div style="grid-column:1/-1;padding:32px;text-align:center;color:rgba(255,255,255,0.4)">
        Še ni zmagovalcev — prvi žreb kmalu
      </div>`;
    return;
  }

  grid.innerHTML = winners.slice(0, 3).map((w, i) => `
    <div class="winner-card">
      <div class="winner-watch-icon">⌚</div>
      <div class="winner-label">Ura #${(totalGiven || winners.length) - i}</div>
      <div class="winner-wallet">${shortWallet(w.wallet)}</div>
      <div class="winner-amount">+$${w.amount_usd.toFixed(0)} SOL</div>
      <div class="winner-time">${timeAgo(w.won_at)}</div>
    </div>
  `).join('');
}

// ── Filter tabs ──────────────────────────────────────────────────

function applyFilter(filter) {
  document.querySelectorAll('.callout-row').forEach(row => {
    if (filter === 'all') {
      row.style.display = '';
    } else {
      const filters = (row.dataset.filter || '').split(' ');
      row.style.display = filters.includes(filter) ? '' : 'none';
    }
  });
}

// Delegirani listener za tab klike (deluje tudi po dinamičnem renderiranju)
document.addEventListener('click', e => {
  const tab = e.target.closest('.callout-tab');
  if (!tab) return;
  document.querySelectorAll('.callout-tab').forEach(t => t.classList.remove('active'));
  tab.classList.add('active');
  applyFilter(tab.dataset.filter);
});

// Search (delegiran)
document.addEventListener('input', e => {
  if (!e.target.matches('.callout-search input')) return;
  const q = e.target.value.toLowerCase();
  document.querySelectorAll('.callout-row').forEach(row => {
    const addr = row.querySelector('.wallet-addr');
    const txt  = addr ? addr.textContent.toLowerCase() : '';
    row.style.display = (!q || txt.includes(q)) ? '' : 'none';
  });
});

// ── Glavni update ────────────────────────────────────────────────

let _offline = false;

async function updateDashboard() {
  let data;
  try {
    const resp = await fetch(API_URL);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    data = await resp.json();

    if (_offline) {
      // Bot je spet online — obnovi barve
      document.querySelectorAll('.countdown-value, .stat-value').forEach(el => {
        el.style.opacity = '';
      });
      _offline = false;
    }
  } catch (err) {
    if (!_offline) {
      console.warn('[SolWatch] API nedosegljiv:', err.message);
      // Pokaži vizualni znak da je bot offline
      document.querySelectorAll('.countdown-value, .stat-value').forEach(el => {
        el.style.opacity = '0.35';
      });
      _offline = true;
    }
    return; // Ne posodabljaj UI z zastarelimi podatki
  }

  // ── Counter & Progress ──────────────────────────────────────────
  const acc    = data.accumulated_usd  || 0;
  const target = data.target_usd       || 200;
  const pct    = data.progress_pct     || 0;

  // Animiraj counter vrednosti
  setText('acc', acc.toFixed(2));
  setText('left', Math.max(0, target - acc).toFixed(2));
  setText('pct', pct.toFixed(1) + '%');
  setWidth('bar', pct);

  // ── Stats strip ─────────────────────────────────────────────────
  setText('winners',       data.watches_given || 0);
  setText('dist',          (data.total_distributed_usd || 0).toFixed(0));
  setText('eligible-count', (data.eligible_holders || []).length);

  // SOL cena (če dodaš element z id="sol-price" v HTML)
  const solPriceEl = document.getElementById('sol-price');
  if (solPriceEl && data.sol_price_usd) {
    solPriceEl.textContent = '$' + data.sol_price_usd.toFixed(2);
  }

  // ── Sekcije ─────────────────────────────────────────────────────
  renderLeaderboard(data.eligible_holders || []);
  renderCallouts(data.eligible_holders || [], data.disqualified || []);
  renderWinners(data.recent_winners || [], data.watches_given || 0);
}

// Zaženi takoj in nato vsakih 5 sekund
updateDashboard();
setInterval(updateDashboard, POLL_MS);
