import os
from dotenv import load_dotenv

load_dotenv()

# Used to sign the session cookie (which holds only a random session id, never
# an API key). Set a real random value in production — see README/.env.example.
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "") or "dev-only-insecure-secret-change-me"

# Set to "true" once you're deployed behind HTTPS (e.g. on Render) so the
# session cookie is marked Secure. Leave false for local http://localhost dev.
FORCE_SECURE_COOKIES = os.environ.get("FORCE_SECURE_COOKIES", "false").strip().lower() == "true"

# Hard cap requested in the spec: 5 tickers per user's watchlist.
MAX_WATCHLIST = 5

DEFAULT_WATCHLIST = [
    t.strip().upper() for t in os.environ.get(
        "DEFAULT_WATCHLIST", "AAPL,MSFT,NVDA,SPY,BTC-USD"
    ).split(",") if t.strip()
][:MAX_WATCHLIST]

# How long (seconds) a computed snapshot for one ticker is reused before
# re-fetching. Keeps a page full of polling browsers from hammering the data
# provider / Groq on every 15-second heartbeat.
STATE_CACHE_SECONDS = int(os.environ.get("STATE_CACHE_SECONDS", "30"))

DISPLAY_TIMEZONE = os.environ.get("DISPLAY_TIMEZONE", "America/Toronto")
DATA_INTERVAL = os.environ.get("DATA_INTERVAL", "15m")
DATA_PERIOD = os.environ.get("DATA_PERIOD", "5d")

# Higher timeframe used to confirm (or contradict) the primary-timeframe signal.
CONFIRM_INTERVAL = os.environ.get("CONFIRM_INTERVAL", "1h")
CONFIRM_PERIOD = os.environ.get("CONFIRM_PERIOD", "30d")

# Optional exact TradingView symbol overrides, e.g. "AAPL:NASDAQ:AAPL,SPY:AMEX:SPY"
_tv_overrides_raw = os.environ.get("TV_SYMBOL_OVERRIDES", "")
TV_SYMBOL_OVERRIDES = {}
for pair in _tv_overrides_raw.split(","):
    if ":" in pair:
        tick, sym = pair.split(":", 1)
        TV_SYMBOL_OVERRIDES[tick.strip()] = sym.strip()

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# Reference trade plan formula knobs.
STOP_ATR_MULT = float(os.environ.get("STOP_ATR_MULT", "1.5"))
ENTRY_PULLBACK_ATR_MULT = float(os.environ.get("ENTRY_PULLBACK_ATR_MULT", "0.5"))
REWARD_RISK_RATIO = float(os.environ.get("REWARD_RISK_RATIO", "2.0"))
HIST_LOOKAHEAD_BARS = int(os.environ.get("HIST_LOOKAHEAD_BARS", "40"))

FEED_MAX_ITEMS = 100

# Exchange codes Yahoo Finance's search API uses for Nasdaq-listed symbols —
# used to sort Nasdaq results to the top of the search dropdown.
NASDAQ_EXCHANGE_CODES = {"NMS", "NGM", "NCM", "NASDAQ"}
