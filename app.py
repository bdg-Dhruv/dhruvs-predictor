import threading
import time
from datetime import datetime, timezone
from functools import wraps

import pandas as pd
import requests
import yfinance as yf
from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for

import auth
import config
import groq_client
import indicators

app = Flask(__name__)
app.config.update(
    SECRET_KEY=config.FLASK_SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=config.FORCE_SECURE_COOKIES,
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 14,  # 14 days
)


# ---------------------------------------------------------------------------
# Auth plumbing — see auth.py for the actual session store.
# ---------------------------------------------------------------------------

def login_required(f):
    """For normal page routes: bounce to /login if not signed in."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        sess = auth.get_session(session.get("sid"))
        if sess is None:
            return redirect(url_for("login"))
        g.user_session = sess
        return f(*args, **kwargs)
    return wrapper


def api_login_required(f):
    """For fetch()-driven API routes: return 401 JSON instead of a redirect."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        sess = auth.get_session(session.get("sid"))
        if sess is None:
            return jsonify({"error": "Not signed in.", "login_required": True}), 401
        g.user_session = sess
        return f(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        groq_key = request.form.get("groq_key", "").strip()
        alpaca_key = request.form.get("alpaca_key", "").strip()
        alpaca_secret = request.form.get("alpaca_secret", "").strip()

        if not groq_key:
            error = "A Groq API key is required."
        else:
            ok, err = auth.validate_groq_key(groq_key)
            if not ok:
                error = f"That Groq API key didn't validate: {err}"
            else:
                ok2, err2 = auth.validate_alpaca_keys(alpaca_key, alpaca_secret)
                if not ok2:
                    error = f"Those Alpaca keys didn't validate: {err2}"
                else:
                    sid = auth.create_session(groq_key, alpaca_key, alpaca_secret)
                    session.clear()
                    session.permanent = True
                    session["sid"] = sid
                    return redirect(url_for("dashboard"))
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    auth.destroy_session(session.get("sid"))
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Data fetching — provider chosen per-user (their own Alpaca keys, or the
# free yfinance fallback).
# ---------------------------------------------------------------------------

def interval_to_minutes(interval_str):
    s = (interval_str or "").strip().lower()
    try:
        if s.endswith("mo"):
            return int(s[:-2]) * 43200
        if s.endswith("wk"):
            return int(s[:-2]) * 10080
        if s.endswith("d"):
            return int(s[:-1]) * 1440
        if s.endswith("h"):
            return int(s[:-1]) * 60
        if s.endswith("m"):
            return int(s[:-1])
    except ValueError:
        pass
    return 15


def format_duration_minutes(total_minutes):
    if total_minutes < 60:
        return f"{total_minutes} min"
    if total_minutes < 1440:
        hours = total_minutes / 60
        return f"{hours:.1f} hr"
    days = total_minutes / 1440
    return f"{days:.1f} days"


def fetch_ticker_df(ticker, interval, period, sess):
    if auth.has_alpaca(sess):
        import alpaca_data
        df = alpaca_data.fetch_bars(ticker, interval, period, sess["alpaca_key"], sess["alpaca_secret"])
    else:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    df = df.dropna()
    if df.empty:
        raise ValueError("no data returned")
    df = localize_index(df)
    return df


def localize_index(df):
    """Convert the dataframe index to the configured display timezone.
    Data providers return tz-aware UTC (or exchange-local) timestamps; without
    this the chart clock won't match what TradingView shows."""
    try:
        idx = df.index
        if idx.tz is None:
            idx = idx.tz_localize("UTC")
        df = df.copy()
        df.index = idx.tz_convert(config.DISPLAY_TIMEZONE)
    except Exception:
        pass
    return df


def to_chart_time(ts):
    """Lightweight Charts interprets a bare Unix timestamp as UTC. To make the
    chart display local wall-clock time, shift by the UTC offset so the
    rendered clock matches TradingView's local view."""
    offset = ts.utcoffset()
    offset_seconds = offset.total_seconds() if offset else 0
    return int(ts.timestamp() + offset_seconds)


def tradingview_symbol(ticker):
    """Best-effort guess at a TradingView symbol. The embedded widget also
    lets the user change the symbol interactively if this guess is off."""
    override = config.TV_SYMBOL_OVERRIDES.get(ticker)
    if override:
        return override
    if ticker.upper().endswith("-USD"):
        base = ticker.upper().replace("-USD", "")
        return f"COINBASE:{base}USD"
    return ticker


def search_symbols(query):
    """Look up stocks, ETFs, and crypto by name or ticker via Yahoo Finance's
    public search endpoint, with Nasdaq-listed results sorted to the top
    (per the spec: source as many results from Nasdaq as possible). Free and
    widely used, but unofficial; if it ever changes shape upstream, this just
    returns an empty list gracefully."""
    query = (query or "").strip()
    if not query:
        return []
    try:
        resp = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": query, "quotesCount": 20, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SignalDesk/1.0"},
            timeout=5,
        )
        data = resp.json()
    except Exception:
        return []

    out = []
    for q in data.get("quotes", []):
        symbol = q.get("symbol")
        if not symbol:
            continue
        exch = (q.get("exchange") or "").upper()
        out.append({
            "symbol": symbol,
            "name": q.get("shortname") or q.get("longname") or symbol,
            "exchange": exch,
            "type": q.get("quoteType", ""),
            "_nasdaq": exch in config.NASDAQ_EXCHANGE_CODES,
        })

    # Stable sort: Nasdaq-listed symbols first, Yahoo's own relevance order
    # preserved within each group.
    out.sort(key=lambda r: 0 if r["_nasdaq"] else 1)
    for r in out:
        del r["_nasdaq"]
    return out[:12]


def fetch_news(ticker, limit=5):
    """Recent headlines for a ticker via yfinance. Defensive about schema
    since yfinance's news payload shape has changed across versions."""
    try:
        raw_items = yf.Ticker(ticker).news or []
    except Exception:
        return []

    out = []
    for item in raw_items[:limit]:
        content = item.get("content", item) if isinstance(item, dict) else {}
        title = content.get("title") or item.get("title")
        if not title:
            continue
        provider = content.get("provider")
        publisher = provider.get("displayName") if isinstance(provider, dict) else item.get("publisher")
        canonical = content.get("canonicalUrl")
        link = canonical.get("url") if isinstance(canonical, dict) else item.get("link")
        out.append({"title": title, "publisher": publisher or "unknown source", "link": link or ""})
    return out


# ---------------------------------------------------------------------------
# Per-user watchlist scanning — computed on demand (cached briefly) rather
# than by one shared background thread, since every user now has their own
# watchlist and their own API keys to call with.
# ---------------------------------------------------------------------------

def compute_ticker_snapshot(ticker, sess):
    cache = sess.setdefault("cache", {})
    now = time.time()
    cached = cache.get(ticker)
    if cached and (now - cached["ts"]) < config.STATE_CACHE_SECONDS:
        return cached["data"]

    df = fetch_ticker_df(ticker, config.DATA_INTERVAL, config.DATA_PERIOD, sess)
    df = indicators.compute_all(df)
    last = df.iloc[-1]
    prev_close = df.iloc[-2]["Close"] if len(df) > 1 else last["Close"]
    change_pct = ((last["Close"] - prev_close) / prev_close) * 100 if prev_close else 0.0

    composite = indicators.compute_composite(df)
    sigs = indicators.detect_signals(df)
    bar_ts = df.index[-1].isoformat()
    active_types = [s["type"] for s in sigs]

    new_feed_entries = []
    for sig in sigs:
        key = (ticker, sig["type"], bar_ts)
        if key in sess["seen_signals"]:
            continue
        sess["seen_signals"].add(key)
        try:
            client = auth.get_groq_client(sess)
            commentary = groq_client.explain_signal(client, ticker, sig["type"], sig["detail"], last)
        except Exception as e:
            commentary = f"AI commentary unavailable right now ({e})."
        new_feed_entries.append({
            "ticker": ticker,
            "type": sig["type"],
            "detail": sig["detail"],
            "commentary": commentary,
            "time": datetime.now(timezone.utc).isoformat(),
        })

    data = {
        "ticker": ticker,
        "price": round(float(last["Close"]), 2),
        "change_pct": round(float(change_pct), 2),
        "active_signals": active_types,
        "composite_label": composite["label"],
        "composite_score": composite["score"],
    }
    cache[ticker] = {"ts": now, "data": data}
    if new_feed_entries:
        sess["feed"] = (new_feed_entries + sess["feed"])[:config.FEED_MAX_ITEMS]
    return data


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    sess = g.user_session
    return render_template(
        "dashboard.html",
        watchlist=sess["watchlist"],
        max_watchlist=config.MAX_WATCHLIST,
    )


@app.route("/chart/<ticker>")
@login_required
def chart_page(ticker):
    return render_template("chart.html", ticker=ticker.upper())


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.route("/api/state")
@api_login_required
def api_state():
    sess = g.user_session
    rows, errors = [], []
    for ticker in sess["watchlist"]:
        try:
            rows.append(compute_ticker_snapshot(ticker, sess))
        except Exception as e:
            errors.append(f"{ticker}: {e}")
    return jsonify({
        "watchlist": rows,
        "feed": sess["feed"][:50],
        "last_run": datetime.now(timezone.utc).isoformat(),
        "errors": errors[-10:],
    })


@app.route("/api/refresh", methods=["POST"])
@api_login_required
def api_refresh():
    sess = g.user_session
    for ticker in sess["watchlist"]:
        sess.get("cache", {}).pop(ticker, None)
    return jsonify({"status": "refresh started"})


@app.route("/api/search")
@api_login_required
def api_search():
    return jsonify(search_symbols(request.args.get("q", "")))


@app.route("/api/watchlist", methods=["GET"])
@api_login_required
def api_watchlist_get():
    sess = g.user_session
    return jsonify({"watchlist": sess["watchlist"], "max": config.MAX_WATCHLIST})


@app.route("/api/watchlist/add", methods=["POST"])
@api_login_required
def api_watchlist_add():
    sess = g.user_session
    payload = request.get_json(silent=True) or {}
    ticker = (payload.get("ticker") or "").strip().upper()
    if not ticker:
        return jsonify({"error": "No ticker given."}), 400
    if ticker in sess["watchlist"]:
        return jsonify({"watchlist": sess["watchlist"]})
    if len(sess["watchlist"]) >= config.MAX_WATCHLIST:
        return jsonify({
            "error": f"Your watchlist is full ({config.MAX_WATCHLIST} max) — remove one first.",
            "watchlist": sess["watchlist"],
        }), 400
    sess["watchlist"].append(ticker)
    return jsonify({"watchlist": sess["watchlist"]})


@app.route("/api/watchlist/remove", methods=["POST"])
@api_login_required
def api_watchlist_remove():
    sess = g.user_session
    payload = request.get_json(silent=True) or {}
    ticker = (payload.get("ticker") or "").strip().upper()
    sess["watchlist"] = [t for t in sess["watchlist"] if t != ticker]
    sess.get("cache", {}).pop(ticker, None)
    return jsonify({"watchlist": sess["watchlist"]})


@app.route("/api/ticker/<ticker>")
@api_login_required
def api_ticker(ticker):
    """Candles + markers for the annotated chart, plus the composite
    reasoning breakdown and an AI narrative grounded in that breakdown."""
    sess = g.user_session
    ticker = ticker.upper()
    try:
        df = fetch_ticker_df(ticker, config.DATA_INTERVAL, config.DATA_PERIOD, sess)
        df = indicators.compute_all(df)

        try:
            confirm_df = fetch_ticker_df(ticker, config.CONFIRM_INTERVAL, config.CONFIRM_PERIOD, sess)
            confirm_df = indicators.compute_all(confirm_df)
            confirm_composite = indicators.compute_composite(confirm_df)
        except Exception:
            confirm_composite = None

        composite = indicators.compute_composite(df)

        mtf_confirmed = False
        if confirm_composite is not None:
            bullish = composite["label"] in indicators.BULLISH_LABELS and confirm_composite["label"] in indicators.BULLISH_LABELS
            bearish = composite["label"] in indicators.BEARISH_LABELS and confirm_composite["label"] in indicators.BEARISH_LABELS
            mtf_confirmed = bullish or bearish

        support, resistance = indicators.support_resistance(df)
        outlook = indicators.compute_outlook(df)
        news_items = fetch_news(ticker)

        trade_plan = indicators.compute_trade_plan(
            df, composite,
            stop_atr_mult=config.STOP_ATR_MULT,
            entry_pullback_atr_mult=config.ENTRY_PULLBACK_ATR_MULT,
            reward_risk_ratio=config.REWARD_RISK_RATIO,
            hist_lookahead=config.HIST_LOOKAHEAD_BARS,
        )
        if trade_plan.get("historical_time_to_target"):
            bars = trade_plan["historical_time_to_target"]["median_bars"]
            minutes = bars * interval_to_minutes(config.DATA_INTERVAL)
            trade_plan["historical_time_label"] = format_duration_minutes(minutes)

        recent = df.tail(300)
        events = indicators.detect_signal_events(recent)

        candles = [
            {"time": to_chart_time(ts), "open": float(r.Open), "high": float(r.High),
             "low": float(r.Low), "close": float(r.Close)}
            for ts, r in recent.iterrows()
        ]
        volumes = [
            {"time": to_chart_time(ts), "value": float(r.Volume),
             "color": "#5DA97C" if r.Close >= r.Open else "#C2594C"}
            for ts, r in recent.iterrows()
        ]
        markers = [
            {"time": to_chart_time(ts),
             "position": "belowBar" if direction == "bull" else "aboveBar",
             "color": "#5DA97C" if direction == "bull" else "#C2594C",
             "shape": "arrowUp" if direction == "bull" else "arrowDown",
             "text": label}
            for ts, label, direction in events
        ]

        last_bar_ts = df.index[-1]
        now_local = datetime.now(timezone.utc).astimezone(last_bar_ts.tzinfo)
        age_minutes = int((now_local - last_bar_ts).total_seconds() / 60)
        data_age = {
            "last_bar_time": last_bar_ts.strftime("%Y-%m-%d %H:%M %Z"),
            "age_minutes": age_minutes,
            "timezone": str(config.DISPLAY_TIMEZONE),
        }

        client = auth.get_groq_client(sess)

        try:
            if confirm_composite is not None:
                narrative = groq_client.synthesize_reasoning(client, ticker, composite, confirm_composite, mtf_confirmed)
            else:
                narrative = "Higher-timeframe data unavailable for this ticker right now."
        except Exception as e:
            narrative = f"AI narrative unavailable right now ({e})."

        try:
            outlook_narrative = groq_client.synthesize_outlook(
                client, ticker, outlook, news_items, composite, confirm_composite
            )
        except Exception as e:
            outlook_narrative = f"AI outlook unavailable right now ({e})."

        try:
            trade_plan_narrative = groq_client.synthesize_trade_plan(client, ticker, trade_plan, composite)
        except Exception as e:
            trade_plan_narrative = f"AI plan explanation unavailable right now ({e})."

        try:
            dummy_explanation = groq_client.synthesize_dummy_explanation(
                client, ticker, composite, outlook, trade_plan, confirm_composite
            )
        except Exception as e:
            dummy_explanation = f"AI plain-English explanation unavailable right now ({e})."

        return jsonify({
            "ticker": ticker,
            "tv_symbol": tradingview_symbol(ticker),
            "candles": candles,
            "volumes": volumes,
            "markers": markers,
            "composite": composite,
            "confirm_composite": confirm_composite,
            "mtf_confirmed": mtf_confirmed,
            "support": round(support, 2),
            "resistance": round(resistance, 2),
            "narrative": narrative,
            "outlook": outlook,
            "outlook_narrative": outlook_narrative,
            "news": news_items,
            "trade_plan": trade_plan,
            "trade_plan_narrative": trade_plan_narrative,
            "dummy_explanation": dummy_explanation,
            "data_age": data_age,
            "in_watchlist": ticker in sess["watchlist"],
            "watchlist_count": len(sess["watchlist"]),
            "watchlist_max": config.MAX_WATCHLIST,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
