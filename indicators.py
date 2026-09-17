"""
Technical indicator calculations, a rule-based composite buy/sell scoring
engine, and historical signal-event detection for chart markers.
Everything here is computed locally from OHLCV data — no external calls.
"""
import pandas as pd

BULLISH_LABELS = ("BUY", "STRONG BUY")
BEARISH_LABELS = ("SELL", "STRONG SELL")


# ---------------------------------------------------------------------------
# Core indicators
# ---------------------------------------------------------------------------

def add_vwap(df):
    df = df.copy()
    day = df.index.date
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    tpv = typical * df["Volume"]
    df["cum_tpv"] = tpv.groupby(day).cumsum()
    df["cum_vol"] = df["Volume"].groupby(day).cumsum()
    df["VWAP"] = df["cum_tpv"] / df["cum_vol"]
    return df


def add_macd(df, fast=12, slow=26, signal=9):
    df = df.copy()
    ema_fast = df["Close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["Close"].ewm(span=slow, adjust=False).mean()
    df["MACD"] = ema_fast - ema_slow
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=signal, adjust=False).mean()
    df["MACD_HIST"] = df["MACD"] - df["MACD_SIGNAL"]
    return df


def add_moving_averages(df, fast=20, slow=50):
    df = df.copy()
    df[f"MA{fast}"] = df["Close"].rolling(fast).mean()
    df[f"MA{slow}"] = df["Close"].rolling(slow).mean()
    return df


def _true_range(df):
    return pd.concat([
        df["High"] - df["Low"],
        (df["High"] - df["Close"].shift()).abs(),
        (df["Low"] - df["Close"].shift()).abs(),
    ], axis=1).max(axis=1)


def add_atr(df, length=14):
    df = df.copy()
    df["ATR"] = _true_range(df).ewm(alpha=1 / length, adjust=False).mean()
    return df


def add_squeeze(df, bb_len=20, bb_mult=2.0, kc_len=20, kc_mult=1.5):
    """TTM-style squeeze: Bollinger Bands compressed inside Keltner Channel."""
    df = df.copy()
    basis = df["Close"].rolling(bb_len).mean()
    dev = bb_mult * df["Close"].rolling(bb_len).std()
    df["BB_UP"] = basis + dev
    df["BB_DOWN"] = basis - dev

    atr = _true_range(df).rolling(kc_len).mean()
    kc_basis = df["Close"].rolling(kc_len).mean()
    df["KC_UP"] = kc_basis + kc_mult * atr
    df["KC_DOWN"] = kc_basis - kc_mult * atr

    df["SQUEEZE_ON"] = (df["BB_DOWN"] > df["KC_DOWN"]) & (df["BB_UP"] < df["KC_UP"])
    df["SQUEEZE_MOMENTUM"] = df["Close"] - df["Close"].rolling(kc_len).mean()
    return df


def add_bollinger(df, length=20, mult=2.0):
    df = df.copy()
    basis = df["Close"].rolling(length).mean()
    dev = mult * df["Close"].rolling(length).std()
    upper = basis + dev
    lower = basis - dev
    df["BOLL_UP"] = upper
    df["BOLL_LOW"] = lower
    df["PERCENT_B"] = (df["Close"] - lower) / (upper - lower)
    return df


def add_rsi(df, length=14):
    df = df.copy()
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
    rs = avg_gain / avg_loss
    df["RSI"] = 100 - (100 / (1 + rs))
    return df


def add_stochastic(df, k=14, d=3, smooth=3):
    df = df.copy()
    low_min = df["Low"].rolling(k).min()
    high_max = df["High"].rolling(k).max()
    raw_k = 100 * (df["Close"] - low_min) / (high_max - low_min)
    df["STOCH_K"] = raw_k.rolling(smooth).mean()
    df["STOCH_D"] = df["STOCH_K"].rolling(d).mean()
    return df


def add_adx(df, length=14):
    df = df.copy()
    up_move = df["High"].diff()
    down_move = -df["Low"].diff()
    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (down_move > 0)) * down_move

    atr = _true_range(df).ewm(alpha=1 / length, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    df["ADX"] = dx.ewm(alpha=1 / length, adjust=False).mean()
    df["PLUS_DI"] = plus_di
    df["MINUS_DI"] = minus_di
    return df


def add_volume_stats(df, length=20):
    df = df.copy()
    avg_vol = df["Volume"].rolling(length).mean()
    df["VOL_REL"] = df["Volume"] / avg_vol
    return df


def compute_all(df):
    df = add_vwap(df)
    df = add_macd(df)
    df = add_moving_averages(df)
    df = add_squeeze(df)
    df = add_bollinger(df)
    df = add_rsi(df)
    df = add_stochastic(df)
    df = add_adx(df)
    df = add_atr(df)
    df = add_volume_stats(df)
    return df


def support_resistance(df, lookback=40):
    """Nearest recent swing support/resistance, purely descriptive."""
    recent = df.iloc[-lookback:] if len(df) >= lookback else df
    return float(recent["Low"].min()), float(recent["High"].max())


# ---------------------------------------------------------------------------
# Candlestick pattern recognition — deterministic, well-established formulas.
# These describe shapes in the data; they are not predictions on their own.
# ---------------------------------------------------------------------------

def _body(bar):
    return abs(bar["Close"] - bar["Open"])


def _range(bar):
    return bar["High"] - bar["Low"]


def detect_candlestick_patterns(df, lookback=15):
    """Return patterns found in the last `lookback` bars, most recent last."""
    patterns = []
    recent = df.tail(lookback + 2)  # small buffer for 2-3 bar patterns
    idxs = list(recent.index)

    for i in range(1, len(idxs)):
        curr = recent.loc[idxs[i]]
        prev = recent.loc[idxs[i - 1]]
        rng = _range(curr)
        if rng == 0 or pd.isna(rng):
            continue
        body = _body(curr)
        upper_wick = curr["High"] - max(curr["Open"], curr["Close"])
        lower_wick = min(curr["Open"], curr["Close"]) - curr["Low"]

        # Bullish engulfing
        if prev["Close"] < prev["Open"] and curr["Close"] > curr["Open"] \
                and curr["Close"] >= prev["Open"] and curr["Open"] <= prev["Close"]:
            patterns.append({"time": idxs[i], "pattern": "Bullish engulfing", "direction": "bull"})
        # Bearish engulfing
        elif prev["Close"] > prev["Open"] and curr["Close"] < curr["Open"] \
                and curr["Open"] >= prev["Close"] and curr["Close"] <= prev["Open"]:
            patterns.append({"time": idxs[i], "pattern": "Bearish engulfing", "direction": "bear"})
        # Hammer: small body near the top, long lower wick
        elif lower_wick > body * 2 and upper_wick < body * 0.6 and body > 0:
            patterns.append({"time": idxs[i], "pattern": "Hammer", "direction": "bull"})
        # Shooting star: small body near the bottom, long upper wick
        elif upper_wick > body * 2 and lower_wick < body * 0.6 and body > 0:
            patterns.append({"time": idxs[i], "pattern": "Shooting star", "direction": "bear"})
        # Doji: body is a tiny fraction of the range
        elif body < rng * 0.1:
            patterns.append({"time": idxs[i], "pattern": "Doji", "direction": "neutral"})

    # keep only the ones inside the requested lookback window
    cutoff = idxs[-lookback] if len(idxs) > lookback else idxs[0]
    return [p for p in patterns if p["time"] >= cutoff]


# ---------------------------------------------------------------------------
# Trend / momentum outlook — a hedged, descriptive read on recent price
# action combined with pattern bias. This is NOT a prediction; it describes
# what the recent data shows and should always be presented with that framing.
# ---------------------------------------------------------------------------

def compute_outlook(df, lookback=20):
    closes = df["Close"].tail(lookback)
    x = list(range(len(closes)))
    if len(closes) >= 2:
        slope = pd.Series(closes.values).diff().mean()
        slope_pct = (slope / closes.mean()) * 100 if closes.mean() else 0.0
    else:
        slope_pct = 0.0

    roc = 0.0
    if len(df["Close"]) > lookback and df["Close"].iloc[-lookback] != 0:
        roc = ((df["Close"].iloc[-1] - df["Close"].iloc[-lookback]) / df["Close"].iloc[-lookback]) * 100

    if slope_pct > 0.05:
        trend_direction = "up"
    elif slope_pct < -0.05:
        trend_direction = "down"
    else:
        trend_direction = "sideways"

    patterns = detect_candlestick_patterns(df, lookback=15)
    bull_count = sum(1 for p in patterns if p["direction"] == "bull")
    bear_count = sum(1 for p in patterns if p["direction"] == "bear")
    if bull_count > bear_count:
        pattern_bias = "bullish"
    elif bear_count > bull_count:
        pattern_bias = "bearish"
    else:
        pattern_bias = "mixed / none"

    return {
        "trend_direction": trend_direction,
        "slope_pct_per_bar": round(float(slope_pct), 3),
        "roc_pct": round(float(roc), 2),
        "pattern_bias": pattern_bias,
        "recent_patterns": [
            {"time": p["time"].isoformat(), "pattern": p["pattern"], "direction": p["direction"]}
            for p in patterns
        ],
    }


# ---------------------------------------------------------------------------
# Reference trade plan — a transparent, rule-based entry/stop/target formula
# (ATR-based risk, support/resistance-aware, configurable reward:risk).
# This is a mechanical reference level derived from the same indicator data
# already computed above. It is NOT a personalized recommendation, and fills,
# stops, and targets are never guaranteed — that framing must travel with
# this data wherever it's displayed.
# ---------------------------------------------------------------------------

def historical_time_to_move(df, distance, max_lookahead=40, sample_bars=250):
    """How many bars, historically, did it actually take this ticker's own
    price to move at least `distance`? A real backtested frequency, not a
    guess — used as a rough, honestly-labeled timing reference only."""
    if distance <= 0:
        return None
    closes = df["Close"].tail(sample_bars).values
    n = len(closes)
    times = []
    for i in range(max(0, n - max_lookahead - 1)):
        start = closes[i]
        for j in range(i + 1, min(i + max_lookahead, n)):
            if abs(closes[j] - start) >= distance:
                times.append(j - i)
                break
    if not times:
        return None
    times.sort()
    median = times[len(times) // 2]
    return {"median_bars": int(median), "sample_size": len(times)}


def compute_trade_plan(df, composite, stop_atr_mult=1.5, entry_pullback_atr_mult=0.5,
                        reward_risk_ratio=2.0, hist_lookahead=40):
    last = df.iloc[-1]
    atr = float(last["ATR"]) if pd.notna(last["ATR"]) else None
    close = float(last["Close"])
    support, resistance = support_resistance(df)

    if atr is None or composite["label"] not in (BULLISH_LABELS + BEARISH_LABELS):
        return {
            "direction": "none",
            "reason": ("The composite reading is neutral, or volatility data isn't available yet, "
                       "so no reference plan is generated — a plan without a directional edge "
                       "isn't meaningful."),
        }

    if composite["label"] in BULLISH_LABELS:
        entry = round(max(support, close - entry_pullback_atr_mult * atr), 2)
        stop = round(min(entry - stop_atr_mult * atr, support - 0.1 * atr), 2)
        risk = entry - stop
        target = round(entry + risk * reward_risk_ratio, 2)
        direction = "long"
        mechanics = (
            f"This is a limit BUY at {entry}. It only fills if price pulls back down to that level — "
            f"if price keeps rising without a pullback, the order simply never fills."
        )
    else:
        entry = round(min(resistance, close + entry_pullback_atr_mult * atr), 2)
        stop = round(max(entry + stop_atr_mult * atr, resistance + 0.1 * atr), 2)
        risk = stop - entry
        target = round(entry - risk * reward_risk_ratio, 2)
        direction = "short"
        mechanics = (
            f"This is a limit SELL (short) at {entry}. It only fills if price rallies up to that level — "
            f"if price keeps falling without a rally, the order simply never fills."
        )

    reward = abs(target - entry)
    hist = historical_time_to_move(df, reward, max_lookahead=hist_lookahead)

    return {
        "direction": direction,
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk_per_share": round(abs(entry - stop), 2),
        "reward_per_share": round(reward, 2),
        "reward_risk_ratio": reward_risk_ratio,
        "entry_mechanics": mechanics,
        "historical_time_to_target": hist,
    }


# ---------------------------------------------------------------------------
# Composite buy/sell scoring — a deterministic rule engine, not a prediction.
# Every vote is derived directly from the indicator values above, so the
# breakdown returned here is exactly what any narrative generation should
# be grounded in.
# ---------------------------------------------------------------------------

def compute_composite(df):
    last = df.iloc[-1]
    breakdown = []
    score = 0.0
    weight_sum = 0.0

    def vote(name, reading, v, explanation, weight=1.0):
        nonlocal score, weight_sum
        score += v * weight
        weight_sum += weight
        breakdown.append({
            "name": name,
            "reading": reading,
            "vote": "BULLISH" if v > 0 else ("BEARISH" if v < 0 else "NEUTRAL"),
            "explanation": explanation,
        })

    # Trend: fast vs slow moving average
    if last["MA20"] > last["MA50"]:
        vote("Trend (MA20/50)", f"{last['MA20']:.2f} > {last['MA50']:.2f}", 1,
             "Fast average is above the slow average: short-term trend is up.")
    else:
        vote("Trend (MA20/50)", f"{last['MA20']:.2f} < {last['MA50']:.2f}", -1,
             "Fast average is below the slow average: short-term trend is down.")

    # MACD
    if last["MACD_HIST"] > 0:
        vote("MACD", f"histogram {last['MACD_HIST']:.3f}", 1,
             "MACD line sits above its signal line: bullish momentum.")
    else:
        vote("MACD", f"histogram {last['MACD_HIST']:.3f}", -1,
             "MACD line sits below its signal line: bearish momentum.")

    # RSI
    rsi_val = float(last["RSI"])
    if rsi_val >= 70:
        vote("RSI (14)", f"{rsi_val:.1f}", -1, "Above 70: momentum looks stretched, overbought zone.")
    elif rsi_val <= 30:
        vote("RSI (14)", f"{rsi_val:.1f}", 1, "Below 30: momentum looks stretched, oversold zone.")
    elif rsi_val > 50:
        vote("RSI (14)", f"{rsi_val:.1f}", 1, "Above 50: momentum leans bullish.")
    else:
        vote("RSI (14)", f"{rsi_val:.1f}", -1, "Below 50: momentum leans bearish.")

    # Stochastic
    k, d = float(last["STOCH_K"]), float(last["STOCH_D"])
    if k > d and k < 80:
        vote("Stochastic", f"%K {k:.1f} / %D {d:.1f}", 1, "%K crossed above %D outside the overbought zone.")
    elif k < d and k > 20:
        vote("Stochastic", f"%K {k:.1f} / %D {d:.1f}", -1, "%K crossed below %D outside the oversold zone.")
    else:
        vote("Stochastic", f"%K {k:.1f} / %D {d:.1f}", 0, "In an extreme zone; the cross isn't decisive here.")

    # VWAP
    if last["Close"] > last["VWAP"]:
        vote("VWAP", f"{last['Close']:.2f} > {last['VWAP']:.2f}", 1, "Price is trading above session VWAP.")
    else:
        vote("VWAP", f"{last['Close']:.2f} < {last['VWAP']:.2f}", -1, "Price is trading below session VWAP.")

    # Bollinger %B
    pb = float(last["PERCENT_B"])
    if pb > 1:
        vote("Bollinger %B", f"{pb:.2f}", -1, "Price is outside the upper band — extended, watch for mean reversion.")
    elif pb < 0:
        vote("Bollinger %B", f"{pb:.2f}", 1, "Price is outside the lower band — extended, watch for mean reversion.")
    else:
        breakdown.append({"name": "Bollinger %B", "reading": f"{pb:.2f}", "vote": "NEUTRAL",
                           "explanation": "Price is inside the bands — no volatility extreme."})

    # Volume — amplifies whatever the net direction already is
    vol_rel = float(last["VOL_REL"]) if pd.notna(last["VOL_REL"]) else 1.0
    if vol_rel > 1.5:
        direction = 1 if score > 0 else (-1 if score < 0 else 0)
        if direction != 0:
            vote("Volume", f"{vol_rel:.2f}x average", direction,
                 "Volume is running well above average, adding weight to the current move.")
        else:
            breakdown.append({"name": "Volume", "reading": f"{vol_rel:.2f}x average", "vote": "NEUTRAL",
                               "explanation": "Volume is elevated but direction is unclear."})
    else:
        breakdown.append({"name": "Volume", "reading": f"{vol_rel:.2f}x average", "vote": "NEUTRAL",
                           "explanation": "Volume is near its recent average."})

    adx_val = float(last["ADX"]) if pd.notna(last["ADX"]) else 0.0
    pct = (score / weight_sum) * 100 if weight_sum else 0.0

    if adx_val >= 25:
        trend_strength = "strong"
        confidence_mult = 1.15
    elif adx_val < 20:
        trend_strength = "weak / choppy"
        confidence_mult = 0.85
    else:
        trend_strength = "moderate"
        confidence_mult = 1.0

    confidence = min(100.0, abs(pct) * confidence_mult)

    if pct >= 50:
        label = "STRONG BUY"
    elif pct >= 15:
        label = "BUY"
    elif pct <= -50:
        label = "STRONG SELL"
    elif pct <= -15:
        label = "SELL"
    else:
        label = "NEUTRAL"

    return {
        "score": round(pct, 1),
        "confidence": round(confidence, 1),
        "label": label,
        "adx": round(adx_val, 1),
        "trend_strength": trend_strength,
        "breakdown": breakdown,
    }


# ---------------------------------------------------------------------------
# Signal detection: latest bar only (used for the AI commentary feed)
# ---------------------------------------------------------------------------

def detect_signals(df):
    if len(df) < 3:
        return []
    signals = []
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if prev["MACD"] < prev["MACD_SIGNAL"] and last["MACD"] > last["MACD_SIGNAL"]:
        signals.append({"type": "MACD_BULL_CROSS",
                         "detail": f"MACD crossed above its signal line ({last['MACD']:.3f} vs {last['MACD_SIGNAL']:.3f})."})
    if prev["MACD"] > prev["MACD_SIGNAL"] and last["MACD"] < last["MACD_SIGNAL"]:
        signals.append({"type": "MACD_BEAR_CROSS",
                         "detail": f"MACD crossed below its signal line ({last['MACD']:.3f} vs {last['MACD_SIGNAL']:.3f})."})
    if prev["Close"] < prev["VWAP"] and last["Close"] > last["VWAP"]:
        signals.append({"type": "VWAP_RECLAIM",
                         "detail": f"Price moved back above session VWAP ({last['Close']:.2f} vs {last['VWAP']:.2f})."})
    if prev["Close"] > prev["VWAP"] and last["Close"] < last["VWAP"]:
        signals.append({"type": "VWAP_LOSS",
                         "detail": f"Price dropped back below session VWAP ({last['Close']:.2f} vs {last['VWAP']:.2f})."})
    if "MA20" in df.columns and "MA50" in df.columns:
        if prev["MA20"] < prev["MA50"] and last["MA20"] > last["MA50"]:
            signals.append({"type": "MA_GOLDEN_CROSS", "detail": "The 20-period average crossed above the 50-period average."})
        if prev["MA20"] > prev["MA50"] and last["MA20"] < last["MA50"]:
            signals.append({"type": "MA_DEATH_CROSS", "detail": "The 20-period average crossed below the 50-period average."})
    if bool(prev["SQUEEZE_ON"]) and not bool(last["SQUEEZE_ON"]):
        direction = "up" if last["SQUEEZE_MOMENTUM"] > 0 else "down"
        signals.append({"type": f"SQUEEZE_FIRE_{direction.upper()}",
                         "detail": f"A volatility squeeze released to the {direction}side (momentum {last['SQUEEZE_MOMENTUM']:.3f})."})

    return signals


# ---------------------------------------------------------------------------
# Historical signal events across the whole series — used for chart markers
# ---------------------------------------------------------------------------

def detect_signal_events(df):
    events = []

    macd_bull = (df["MACD"] > df["MACD_SIGNAL"]) & (df["MACD"].shift(1) <= df["MACD_SIGNAL"].shift(1))
    macd_bear = (df["MACD"] < df["MACD_SIGNAL"]) & (df["MACD"].shift(1) >= df["MACD_SIGNAL"].shift(1))
    vwap_reclaim = (df["Close"] > df["VWAP"]) & (df["Close"].shift(1) <= df["VWAP"].shift(1))
    vwap_loss = (df["Close"] < df["VWAP"]) & (df["Close"].shift(1) >= df["VWAP"].shift(1))
    ma_bull = (df["MA20"] > df["MA50"]) & (df["MA20"].shift(1) <= df["MA50"].shift(1))
    ma_bear = (df["MA20"] < df["MA50"]) & (df["MA20"].shift(1) >= df["MA50"].shift(1))
    squeeze_fire = df["SQUEEZE_ON"].shift(1).fillna(False) & (~df["SQUEEZE_ON"].fillna(False))

    for idx in df.index[macd_bull.fillna(False)]:
        events.append((idx, "MACD bull cross", "bull"))
    for idx in df.index[macd_bear.fillna(False)]:
        events.append((idx, "MACD bear cross", "bear"))
    for idx in df.index[vwap_reclaim.fillna(False)]:
        events.append((idx, "VWAP reclaim", "bull"))
    for idx in df.index[vwap_loss.fillna(False)]:
        events.append((idx, "VWAP loss", "bear"))
    for idx in df.index[ma_bull.fillna(False)]:
        events.append((idx, "MA golden cross", "bull"))
    for idx in df.index[ma_bear.fillna(False)]:
        events.append((idx, "MA death cross", "bear"))
    for idx in df.index[squeeze_fire]:
        mom = df.loc[idx, "SQUEEZE_MOMENTUM"]
        if mom > 0:
            events.append((idx, "Squeeze fired up", "bull"))
        else:
            events.append((idx, "Squeeze fired down", "bear"))

    events.sort(key=lambda e: e[0])
    return events
