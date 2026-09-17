"""
Multi-user, bring-your-own-key session handling.

Each visitor logs in with their OWN Groq API key (required) and, optionally,
their own Alpaca API key/secret for real-time data. Nobody's key is shared
with anybody else, and no key is ever written to disk or a database.

How it works: at login we validate the keys with one cheap live call each,
then generate a random opaque session id (`sid`) and store the actual keys
+ that user's watchlist/feed/cache in the SESSIONS dict below, in server
memory. The browser only ever receives the random `sid` inside Flask's
signed session cookie — never the raw API keys — so even a stolen/tampered
cookie can't reveal or fabricate credentials.

Honest limitation: this is in-memory and per-process. It's the right amount
of complexity for a small personal/shared tool, but it means:
  - Restarting or redeploying the server logs everyone out (watchlists reset
    too) — same tradeoff the old single-owner version had.
  - It won't work correctly behind a multi-instance/load-balanced deployment
    unless you add a shared store (e.g. Redis) — see README.
"""
import threading
import time
import uuid

from groq import Groq

import config

SESSIONS = {}
_lock = threading.Lock()


def validate_groq_key(api_key):
    """One cheap, low-cost call that fails fast on a bad/expired key."""
    try:
        client = Groq(api_key=api_key)
        client.models.list()
        return True, None
    except Exception as e:
        return False, str(e)


def validate_alpaca_keys(api_key, api_secret):
    """Alpaca keys are optional — only validated if both fields are filled in."""
    if not api_key and not api_secret:
        return True, None
    if bool(api_key) != bool(api_secret):
        return False, "Provide both the Alpaca API key and secret, or leave both blank."
    try:
        from alpaca.trading.client import TradingClient
        client = TradingClient(api_key, api_secret, paper=True)
        client.get_account()
        return True, None
    except Exception as e:
        return False, str(e)


def create_session(groq_key, alpaca_key, alpaca_secret):
    sid = uuid.uuid4().hex
    with _lock:
        SESSIONS[sid] = {
            "groq_key": groq_key,
            "alpaca_key": alpaca_key or "",
            "alpaca_secret": alpaca_secret or "",
            "watchlist": list(config.DEFAULT_WATCHLIST),
            "seen_signals": set(),
            "feed": [],
            "cache": {},
            "groq_client": None,
            "created_at": time.time(),
        }
    return sid


def get_session(sid):
    if not sid:
        return None
    return SESSIONS.get(sid)


def destroy_session(sid):
    if not sid:
        return
    with _lock:
        SESSIONS.pop(sid, None)


def get_groq_client(sess):
    if sess.get("groq_client") is None:
        sess["groq_client"] = Groq(api_key=sess["groq_key"])
    return sess["groq_client"]


def has_alpaca(sess):
    return bool(sess.get("alpaca_key")) and bool(sess.get("alpaca_secret"))
