# Deploying Signal Desk

## 1. Push to GitHub

```bash
cd signal-desk
git init
git add .
git commit -m "Signal Desk"
git branch -M main
git remote add origin https://github.com/<you>/signal-desk.git
git push -u origin main
```

`.gitignore` already excludes `.env` and bytecode — you're not committing
any secrets, because there aren't any global secrets to commit anymore.
Every visitor supplies their own API keys through the site itself.

## 2. Deploy on Render

1. Go to [render.com](https://render.com) → **New** → **Web Service** →
   connect your GitHub repo.
2. Render should detect `render.yaml` automatically and pre-fill the build
   and start commands. If not, set them manually:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn app:app --workers 1 --threads 8 --timeout 120`
3. **Set environment variables** (Render dashboard → Environment):
   - `FLASK_SECRET_KEY` — Render's `generateValue: true` in `render.yaml`
     handles this automatically; otherwise generate one yourself:
     ```bash
     python -c "import secrets; print(secrets.token_hex(32))"
     ```
   - `FORCE_SECURE_COOKIES=true` (Render gives you HTTPS by default)
   - Anything else from `.env.example` you want to change from its default
     (e.g. `DEFAULT_WATCHLIST`, `DISPLAY_TIMEZONE`).
   - **Do NOT** set `GROQ_API_KEY` or `ALPACA_API_KEY` here — there's
     nowhere for the app to read them from anymore. Every user enters their
     own on the login page.
4. Deploy. Once it's live, open the URL and sign in with your own keys to
   confirm everything works end to end.

## Important: keep it at exactly one worker

Sessions (API keys, watchlists) are held in that single process's memory —
see the README's "How the multi-user model actually works" section. If you
change the start command or scale the service to multiple instances/workers,
users will get bounced between processes that don't share memory and will
appear to randomly get logged out or lose their watchlist. Keep
`--workers 1` (Render's free tier only gives you one instance anyway, so
this is the default case, not a special one).

## Free-tier caveats

- The service **sleeps after inactivity** on Render's free plan, and the
  first request after a sleep can take 30–60 seconds to wake it back up.
- **Every session resets on redeploy/restart** — including everyone's
  watchlist. This is a known, documented tradeoff of the in-memory session
  design (see README), not a bug.
- If you need sessions to survive restarts, or want to run more than one
  worker/instance, swap the in-memory `SESSIONS` dict in `auth.py` for a
  Redis-backed or database-backed store — the rest of the app (routes,
  `login_required`/`api_login_required` decorators) doesn't need to change.
