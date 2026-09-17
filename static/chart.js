function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(s);
  });
}

function renderReasoningPanel(data) {
  const composite = data.composite;
  const confirmComposite = data.confirm_composite;

  const labelEl = document.getElementById("composite-label");
  labelEl.textContent = composite.label;
  labelEl.className = "score-label " + composite.label.toLowerCase().replace(/\s+/g, "-");

  document.getElementById("composite-score").textContent = `score ${composite.score}`;
  document.getElementById("composite-confidence").textContent = `${composite.confidence}% confidence`;
  document.getElementById("trend-strength").textContent = `Trend strength: ${composite.trend_strength} (ADX ${composite.adx})`;

  const mtfEl = document.getElementById("mtf-note");
  if (confirmComposite) {
    mtfEl.textContent = data.mtf_confirmed
      ? `Confirmed on the higher timeframe (reads ${confirmComposite.label})`
      : `Not confirmed on the higher timeframe (reads ${confirmComposite.label})`;
    mtfEl.className = "mtf-note " + (data.mtf_confirmed ? "confirmed" : "unconfirmed");
  } else {
    mtfEl.textContent = "Higher-timeframe data unavailable.";
  }

  document.getElementById("sr-levels").textContent =
    `Recent support ${data.support} · Recent resistance ${data.resistance}`;

  document.getElementById("narrative").textContent = data.narrative;

  const list = document.getElementById("breakdown-list");
  list.innerHTML = "";
  composite.breakdown.forEach(b => {
    const div = document.createElement("div");
    div.className = "breakdown-row " + b.vote.toLowerCase();
    div.innerHTML = `
      <div class="breakdown-head">
        <span class="breakdown-name">${b.name}</span>
        <span class="breakdown-vote">${b.vote}</span>
      </div>
      <div class="breakdown-reading">${b.reading}</div>
      <p class="breakdown-explain">${b.explanation}</p>
    `;
    list.appendChild(div);
  });

  document.getElementById("outlook-narrative").textContent = data.outlook_narrative;
  const outlook = data.outlook;
  document.getElementById("outlook-trend").textContent =
    `Trend: ${outlook.trend_direction} (${outlook.roc_pct}% over lookback)`;
  document.getElementById("outlook-patterns").textContent =
    `Pattern bias: ${outlook.pattern_bias}`;

  const newsList = document.getElementById("news-list");
  newsList.innerHTML = "";
  if (!data.news || data.news.length === 0) {
    newsList.innerHTML = '<p class="empty-state">No recent headlines found.</p>';
  } else {
    data.news.forEach(n => {
      const item = document.createElement("a");
      item.className = "news-item";
      item.href = n.link || "#";
      item.target = "_blank";
      item.rel = "noopener noreferrer";
      item.innerHTML = `
        <span class="news-title">${n.title}</span>
        <span class="news-publisher">${n.publisher}</span>
      `;
      newsList.appendChild(item);
    });
  }
}

function renderDataAge(dataAge) {
  const el = document.getElementById("data-age-banner");
  if (!el || !dataAge) return;
  const mins = dataAge.age_minutes;
  el.innerHTML = `
    <strong>Data is ${mins} min old</strong> — last bar ${dataAge.last_bar_time}.
    The free feed is delayed, so any signal here describes a move that has
    <em>already happened</em>. Prices may have moved since. Levels shown are
    reference points, not live entries.
  `;
  el.className = "data-age-banner " + (mins > 20 ? "stale" : "fresh");
}

function renderTradePlan(plan, narrative) {
  const body = document.getElementById("tradeplan-body");
  if (!plan || plan.direction === "none") {
    body.innerHTML = `<p class="empty-state">${(plan && plan.reason) || "No reference plan available."}</p>`;
    return;
  }
  const hist = plan.historical_time_to_target;
  const histTxt = hist
    ? `Historically, moves of this size took about ${plan.historical_time_label || hist.median_bars + " bars"} `
      + `(median across ${hist.sample_size} observed instances in this ticker's own data). Not a guarantee.`
    : "Not enough historical data to estimate typical timing for a move this size.";

  body.innerHTML = `
    <div class="tradeplan-grid">
      <div><span class="tp-label">Direction</span><span class="tp-value">${plan.direction.toUpperCase()}</span></div>
      <div><span class="tp-label">Limit entry</span><span class="tp-value">${plan.entry}</span></div>
      <div><span class="tp-label">Stop loss</span><span class="tp-value">${plan.stop}</span></div>
      <div><span class="tp-label">Take profit</span><span class="tp-value">${plan.target}</span></div>
      <div><span class="tp-label">Risk / Reward</span><span class="tp-value">${plan.risk_per_share} / ${plan.reward_per_share} (${plan.reward_risk_ratio}:1)</span></div>
    </div>
    <p class="tp-mechanics">${plan.entry_mechanics}</p>
    <p class="tp-hist">${histTxt}</p>
    <p class="tp-narrative">${narrative}</p>
  `;
}

function initTabs() {
  document.querySelectorAll(".panel-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".panel-tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById("tab-pro").classList.toggle("hidden", btn.dataset.tab !== "pro");
      document.getElementById("tab-dummy").classList.toggle("hidden", btn.dataset.tab !== "dummy");
    });
  });
}

function initWatchStar(ticker, initiallyIn, watchlistCount, watchlistMax) {
  const starBtn = document.getElementById("watch-star");
  let inWatchlist = initiallyIn;
  let count = watchlistCount;

  function paint() {
    starBtn.classList.toggle("active", inWatchlist);
    starBtn.title = inWatchlist ? "Remove from watchlist" : "Add to watchlist";
  }
  paint();

  starBtn.addEventListener("click", async () => {
    starBtn.disabled = true;
    const endpoint = inWatchlist ? "/api/watchlist/remove" : "/api/watchlist/add";
    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker }),
      });
      const result = await res.json();
      if (res.status === 401) {
        window.location.href = "/login";
        return;
      }
      if (!res.ok) {
        alert(result.error || "Could not update watchlist.");
      } else {
        inWatchlist = !inWatchlist;
        count = (result.watchlist || []).length;
        paint();
      }
    } catch (e) {
      alert("Could not reach the server.");
    }
    starBtn.disabled = false;
  });
}

async function init() {
  const ticker = document.body.dataset.ticker;
  const statusEl = document.getElementById("chart-status");

  try {
    await Promise.all([
      loadScript("https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"),
      loadScript("https://s3.tradingview.com/tv.js"),
    ]);

    const res = await fetch(`/api/ticker/${encodeURIComponent(ticker)}`);
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const data = await res.json();
    if (data.error) {
      statusEl.textContent = "error: " + data.error;
      return;
    }

    // Official TradingView embedded widget — the real chart, exact candles.
    new TradingView.widget({
      autosize: true,
      symbol: data.tv_symbol,
      interval: "15",
      timezone: (data.data_age && data.data_age.timezone) || "America/Toronto",
      theme: "dark",
      style: "1",
      locale: "en",
      toolbar_bg: "#101512",
      enable_publishing: false,
      hide_top_toolbar: false,
      container_id: "tv_widget",
    });

    // Our own annotated chart, built from the same data driving the signals.
    const chart = LightweightCharts.createChart(document.getElementById("lw_chart"), {
      layout: { background: { color: "#101512" }, textColor: "#EAE7DC" },
      grid: { vertLines: { color: "#24302A" }, horzLines: { color: "#24302A" } },
      timeScale: { timeVisible: true, secondsVisible: false },
      height: 360,
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#5DA97C", downColor: "#C2594C", borderVisible: false,
      wickUpColor: "#5DA97C", wickDownColor: "#C2594C",
    });
    candleSeries.setData(data.candles);
    candleSeries.setMarkers(data.markers);

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "",
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volumeSeries.setData(data.volumes);

    window.addEventListener("resize", () => {
      chart.applyOptions({ width: document.getElementById("lw_chart").clientWidth });
    });

    renderReasoningPanel(data);
    renderDataAge(data.data_age);
    renderTradePlan(data.trade_plan, data.trade_plan_narrative);
    document.getElementById("dummy-explanation").textContent = data.dummy_explanation;
    initTabs();
    initWatchStar(data.ticker, data.in_watchlist, data.watchlist_count, data.watchlist_max);
    statusEl.textContent = "live";
  } catch (e) {
    statusEl.textContent = "error loading chart";
    console.error(e);
  }
}

init();
