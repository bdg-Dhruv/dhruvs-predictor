# Signal Desk

A multi-user, bring-your-own-API-key trading signal dashboard: Python computes
real technical indicators, a rule-based scoring engine turns them into a
buy/sell/neutral read, Groq explains *why* in plain English, and it's all
shown on a dashboard — plus a per-ticker chart page with a real TradingView
chart and your own annotated version with buy/sell markers.

Nothing here is financial advice — it's a tool for reading charts faster.

## Multi-user, bring-your-own-key

Anyone can use this site as long as they bring their own API keys:

- **Groq API key — required.** Free at [console.groq.com/keys](https://console.groq.com/keys). Powers every AI narrative on the site.
- **Alpaca API key + secret — optional.** Free at [alpaca.markets](https://alpaca.markets). If provided, you get real-time-ish data instead of the ~15 min delayed free default (see the data-delay section below).

Each visitor signs in with their own keys on the `/login` page. **Nobody's
keys are shared, and no key is ever written to a file or database** — see
"How the multi-user model actually works" below for the exact mechanism.

## Your watchlist

- Up to **5 tickers** per signed-in session.
- On any chart page (`/chart/<ticker>`), click the **star** next to the
  ticker name to add it to your watchlist (it turns yellow/amber).
- On the dashboard, click the **star** next to any watchlist row to remove it
  — the row disappears immediately.
- If you try to add a 6th ticker, you'll get a clear "watchlist is full"
  message — remove one first.
- New sessions start with a default starter watchlist (`AAPL, MSFT, NVDA,
  SPY, BTC-USD` — configurable via `DEFAULT_WATCHLIST` in `.env`); swap any
  of them out via the stars.

## How the multi-user model actually works

There's no database. When you sign in:

1. Your Groq key (and Alpaca keys, if given) are validated with one cheap
   live API call each.
2. A random, meaningless session id is generated and stored in your
   browser's cookie (signed, `httponly`, so it can't be read or forged by
   JavaScript or a tampered client).
3. Your *actual* keys, plus your watchlist, are stored server-side **in that
   process's memory**, keyed by that random id. The browser never holds the
   real keys — only the random pointer to them.

**The honest tradeoff:** this is in-memory and per-process, which is the
right amount of complexity for a small personal or shared tool, but means:

- Restarting or redeploying the server logs *everyone* out and clears every
  watchlist. You'll need to sign back in with your keys.
- It must run as a **single process/worker** (see `Procfile`) — a
  multi-worker or multi-instance deployment would split sessions across
  processes that don't share memory, causing random "you're signed out"
  behavior. If you outgrow this, swap the in-memory dict in `auth.py` for
  Redis or a database-backed session store.
- Treat your own API keys the way you'd treat a password once you're
  entering them into any deployed instance of this app — only run this on
  infrastructure you trust.

## The default data is delayed — here's the real fix

By default this uses Yahoo Finance's free feed, which is **delayed roughly
15 minutes** for most exchanges. There's a genuinely free way around it,
built in:

**Enter your Alpaca keys at login.** [Alpaca Markets](https://alpaca.markets)
gives free accounts real-time data — IEX-feed for stocks/ETFs, and fully
real-time for crypto — with no artificial delay.

1. Sign up free at alpaca.markets
2. Create a paper trading account (no funding required — this app only
   reads market data, it never places trades)
3. Dashboard → API Keys → generate a key + secret
4. Enter them on the Signal Desk login page

**One honest caveat about "real-time."** Alpaca's free stock/ETF feed is IEX
only — one exchange, roughly 2.5% of total US equity volume — not the full
consolidated tape (that requires their paid SIP tier). It is genuinely *not
delayed* the way Yahoo's feed is, but it's a narrower slice of the market
than "every trade everywhere." Crypto data on the free tier has no such
limitation.

**Why the delay matters more than it sounds like it does.** If a signal
appears at 3:45pm based on 3:30pm data, and price rose between 3:30 and
3:45, the indicator didn't *predict* that move — it **measured** it. The
chart page's data-age banner always shows exactly how stale what you're
looking at is, on either provider.

## What's on each page

**Login (`/login`)** — enter your Groq key (required) and optionally your
Alpaca key/secret. Keys are validated once, then held only in server memory
for your session.

**Dashboard (`/`)** — a search bar that finds *any* stock, ETF, or crypto by
name or ticker, plus your watchlist (max 5) with live price, change %, and a
composite signal badge, a star to remove each row, and a feed of AI
commentary as new signals fire on your watchlist tickers.

**Chart page (`/chart/<ticker>`)** — reachable for any ticker via search, not
just ones on your watchlist:
- A **star** next to the ticker name to add/remove it from your watchlist.
- The **real TradingView chart**, embedded via TradingView's own official,
  free widget — candles in their exact real positions, fully interactive.
- Your **own annotated chart** (built with TradingView's open-source
  Lightweight Charts library) with arrow markers on the exact candle where a
  rule fired.
- A **reasoning panel**: composite score, confidence %, ADX trend-strength,
  higher-timeframe confirmation, support/resistance, and a full
  indicator-by-indicator breakdown with an AI narrative grounded in that
  exact breakdown (it's only given real numbers to explain, so it can't
  invent signals that aren't there).
- An **Outlook & News** section: detected candlestick patterns, a
  trend/momentum read, real news headlines, and a hedged AI outlook.
- A **reference trade plan**: a transparent, ATR + support/resistance based
  limit entry/stop/target, with a historical-timing reference labeled as a
  frequency, never a promise.
- A **Detailed / Dummy** toggle that rewrites everything in plain English for
  someone who's never traded before.

## Nasdaq-prioritized search

The search bar queries Yahoo Finance's public search endpoint and sorts
Nasdaq-listed results (exchange codes `NMS`/`NGM`/`NCM`) to the top of the
dropdown, since Nasdaq coverage was specifically requested — while still
surfacing NYSE/AMEX stocks, ETFs, and crypto pairs.

## Composite signal engine

Every reading combines, with an ADX-based confidence adjustment:

| Indicator | What it checks |
|---|---|
| MA20 / MA50 | Short-term trend direction |
| MACD | Momentum, via histogram sign |
| RSI (14) | Overbought / oversold, momentum bias |
| Stochastic (14/3/3) | Short-term momentum turns |
| VWAP | Price above/below session volume-weighted average |
| Bollinger %B | Volatility extremes |
| ADX | Trend strength — dampens or boosts confidence |
| Volume | Confirms or questions the move |

It also pulls a **higher timeframe** (1h by default) and checks whether it
agrees with the primary timeframe (15m by default) — a real confluence
check, not just a single-timeframe snapshot.

This is a deterministic rule engine, not a prediction — it tells you what
the indicators currently show, not what will happen next.

## Local setup

1. Install Python 3.10+.
2. From this folder:
   ```bash
   pip install -r requirements.txt
   ```
   (If a pinned build fails on a very new Python version, install unpinned:
   `pip install flask yfinance pandas groq python-dotenv requests alpaca-py gunicorn`.)
3. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   The defaults work fine for local testing — there are no API keys to add
   here anymore, since every visitor (including you) enters their own on the
   login page. You may still want to set a real `FLASK_SECRET_KEY`.
4. Run it:
   ```bash
   python app.py
   ```
5. Open **http://localhost:5000**, sign in with your own Groq (and optional
   Alpaca) keys.

## Deploying it as a real site

See `DEPLOY.md` for the full walkthrough (Render, one process/worker,
setting `FLASK_SECRET_KEY`).

## Using the Pine Script on TradingView directly

1. Open any chart on TradingView → **Pine Editor**.
2. Paste `pine/signal_desk_indicators.pine` → **Add to Chart**.
3. Optionally add native TradingView alerts on any of its conditions.

This is a separate, independent view of similar signals — Pine Script can't
call Groq directly, so it doesn't feed into the Python dashboard automatically.

## Notes and limits

- Market data is `yfinance` (free, ~15 min delayed) by default, or your own
  Alpaca keys for real-time-ish data.
- Symbol search uses Yahoo Finance's public (unofficial) search endpoint, and
  news comes from yfinance's news feed — both free, no key required, but
  unofficial, so results can occasionally be sparse or the format could
  change upstream.
- The Outlook section (patterns, trend, news synthesis) is a deterministic
  read on recent data plus a hedged AI summary — a description of what the
  data currently shows, not a forecast guarantee.
- The reference trade plan is a mechanical formula (ATR + support/resistance),
  not a personalized recommendation from a licensed advisor. No tool can
  reliably predict short-term price direction or timing; treat every number
  here as a reference point for your own judgment, not an instruction.
- The TradingView symbol shown is a best-effort guess. If it picks the wrong
  exchange, change the symbol inside the embedded widget itself, or set
  `TV_SYMBOL_OVERRIDES` in `.env`.
- Groq's output is instructed to describe the data, not issue buy/sell
  instructions or price predictions.
- Everything computes on demand per signed-in session (max 5 tickers,
  cached for `STATE_CACHE_SECONDS`) rather than one shared background scan —
  each user's own keys make their own calls.
- Watchlists and sessions live in server memory only — see "How the
  multi-user model actually works" above.
- Want to change the scoring logic or add a new indicator? Edit
  `indicators.py` — `compute_composite()` is the scoring engine and
  `detect_signal_events()` drives the chart markers.
