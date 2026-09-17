"""
Optional real-time(r) data source via Alpaca Markets — an alternative to
yfinance for people who want to get past Yahoo's ~15 minute delay.

Each user supplies their OWN Alpaca key/secret at login (see auth.py); this
module takes them as plain arguments rather than reading a single shared
config value, since different visitors may use different accounts.

Honest caveat: Alpaca's free tier gives REAL-TIME data, but for stocks it's
IEX-only (one exchange, roughly 2.5% of total US equity volume) rather than
the full consolidated tape — that requires a paid SIP subscription on their
end. It is NOT artificially delayed the way Yahoo's free feed is, which is
the actual problem this solves, but it isn't literally every trade on every
exchange either. Crypto data on the free tier has no such limitation — it's
fully real-time.

Free setup: sign up at alpaca.markets, create a (no-funding-required) paper
trading account, generate an API key + secret from the dashboard, and enter
them on the Signal Desk login page.
"""
from datetime import datetime, timedelta, timezone

from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit


def _parse_timeframe(interval_str):
    s = interval_str.strip().lower()
    try:
        if s.endswith("m"):
            return TimeFrame(int(s[:-1]), TimeFrameUnit.Minute)
        if s.endswith("h"):
            return TimeFrame(int(s[:-1]), TimeFrameUnit.Hour)
        if s.endswith("d"):
            return TimeFrame(int(s[:-1]), TimeFrameUnit.Day)
    except ValueError:
        pass
    return TimeFrame(15, TimeFrameUnit.Minute)


def _parse_period_to_start(period_str):
    s = period_str.strip().lower()
    now = datetime.now(timezone.utc)
    try:
        if s.endswith("mo"):
            return now - timedelta(days=int(s[:-2]) * 30)
        if s.endswith("wk"):
            return now - timedelta(weeks=int(s[:-2]))
        if s.endswith("y"):
            return now - timedelta(days=int(s[:-1]) * 365)
        if s.endswith("d"):
            return now - timedelta(days=int(s[:-1]))
    except ValueError:
        pass
    return now - timedelta(days=5)


def is_crypto_ticker(ticker):
    return ticker.upper().endswith("-USD") or "/" in ticker


def _to_alpaca_crypto_pair(ticker):
    if "/" in ticker:
        return ticker.upper()
    return ticker.upper().replace("-USD", "/USD")


def fetch_bars(ticker, interval, period, api_key, api_secret):
    """Returns a DataFrame with Open/High/Low/Close/Volume columns and a
    tz-aware UTC DatetimeIndex — same shape fetch_ticker_df expects from
    yfinance, so it drops into the existing pipeline unchanged."""
    if not api_key or not api_secret:
        raise RuntimeError("Alpaca keys are missing for this session.")

    timeframe = _parse_timeframe(interval)
    start = _parse_period_to_start(period)

    if is_crypto_ticker(ticker):
        pair = _to_alpaca_crypto_pair(ticker)
        client = CryptoHistoricalDataClient(api_key, api_secret)
        req = CryptoBarsRequest(symbol_or_symbols=[pair], timeframe=timeframe, start=start)
        bars = client.get_crypto_bars(req)
        df = bars.df
        if df.empty:
            raise ValueError(f"no Alpaca crypto data returned for {pair}")
        if "symbol" in df.index.names:
            df = df.xs(pair, level="symbol")
    else:
        client = StockHistoricalDataClient(api_key, api_secret)
        req = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=timeframe, start=start, feed="iex")
        bars = client.get_stock_bars(req)
        df = bars.df
        if df.empty:
            raise ValueError(f"no Alpaca stock data returned for {ticker}")
        if "symbol" in df.index.names:
            df = df.xs(ticker, level="symbol")

    df = df.rename(columns={
        "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume",
    })[["Open", "High", "Low", "Close", "Volume"]]

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df
