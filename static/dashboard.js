const watchlistBody = document.getElementById("watchlist-body");
const watchlistCount = document.getElementById("watchlist-count");
const feedList = document.getElementById("feed-list");
const feedCount = document.getElementById("feed-count");
const lastRun = document.getElementById("last-run");
const refreshBtn = document.getElementById("refresh-btn");

function fmtTime(iso) {
  if (!iso) return "not run yet";
  const d = new Date(iso);
  return "last scan " + d.toLocaleTimeString();
}

function renderWatchlist(rows) {
  watchlistCount.textContent = `${rows.length}/${MAX_WATCHLIST}`;

  if (rows.length === 0) {
    watchlistBody.innerHTML =
      '<tr><td colspan="5" class="empty-state">Your watchlist is empty. Search above and star a chart to add up to ' +
      MAX_WATCHLIST + ' tickers.</td></tr>';
    return;
  }

  watchlistBody.innerHTML = "";
  rows.forEach(row => {
    const tr = document.createElement("tr");
    tr.dataset.ticker = row.ticker;
    const sign = row.change_pct >= 0 ? "+" : "";
    const badges = (row.active_signals || [])
      .map(sig => `<span class="badge">${sig.replace(/_/g, " ")}</span>`)
      .join("");
    tr.innerHTML = `
      <td class="watch-star"><button class="star-btn active" data-ticker="${row.ticker}" title="Remove from watchlist" type="button">★</button></td>
      <td class="ticker"><a href="/chart/${row.ticker}">${row.ticker}</a></td>
      <td class="price">${row.price.toFixed(2)}</td>
      <td class="change ${row.change_pct >= 0 ? "up" : "down"}">${sign}${row.change_pct.toFixed(2)}%</td>
      <td class="composite ${row.composite_label.toLowerCase().replace(/\s+/g, "-")}">
        ${row.composite_label}
        <div class="badges">${badges}</div>
      </td>
    `;
    watchlistBody.appendChild(tr);
  });
}

function renderFeed(items) {
  feedCount.textContent = items.length;
  if (items.length === 0) {
    feedList.innerHTML = '<p class="empty-state">No signals yet. They\'ll appear here as your watchlist gets scanned.</p>';
    return;
  }
  feedList.innerHTML = "";
  items.forEach(item => {
    const div = document.createElement("div");
    div.className = "feed-item";
    const time = new Date(item.time).toLocaleTimeString();
    div.innerHTML = `
      <div class="feed-item-head">
        <span class="feed-ticker">${item.ticker}</span>
        <span class="feed-type">${item.type.replace(/_/g, " ")}</span>
        <span class="feed-time">${time}</span>
      </div>
      <p class="feed-detail">${item.detail}</p>
      <p class="feed-commentary">${item.commentary}</p>
    `;
    feedList.appendChild(div);
  });
}

async function pollState() {
  try {
    const res = await fetch("/api/state");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const data = await res.json();
    renderWatchlist(data.watchlist);
    renderFeed(data.feed);
    lastRun.textContent = fmtTime(data.last_run);
  } catch (e) {
    lastRun.textContent = "connection error";
  }
}

watchlistBody.addEventListener("click", async (e) => {
  const btn = e.target.closest(".star-btn");
  if (!btn) return;
  const ticker = btn.dataset.ticker;
  btn.disabled = true;
  try {
    await fetch("/api/watchlist/remove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker }),
    });
  } finally {
    await pollState();
  }
});

refreshBtn.addEventListener("click", async () => {
  refreshBtn.disabled = true;
  refreshBtn.textContent = "Scanning…";
  await fetch("/api/refresh", { method: "POST" });
  await pollState();
  refreshBtn.disabled = false;
  refreshBtn.textContent = "Refresh now";
});

pollState();
setInterval(pollState, 20000);
