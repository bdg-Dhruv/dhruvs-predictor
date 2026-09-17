@echo off
REM ---------------------------------------------------------------
REM Signal Desk launcher
REM Starts the Flask app, waits for it to boot, opens the login page.
REM Close this window (or press Ctrl+C) to stop the server.
REM ---------------------------------------------------------------

cd /d "%~dp0"

echo Starting Signal Desk...
echo.
echo You'll enter your own Groq (and optional Alpaca) API keys on the
echo login page that opens in your browser - nothing needed in .env
echo for that anymore.
echo.

REM Open the browser after a short delay, in the background, so the
REM server has time to bind to port 5000 first.
start "" /b cmd /c "timeout /t 4 /nobreak >nul && start http://localhost:5000"

REM Run the app in this window so you can see logs and Ctrl+C to stop.
py app.py

REM If py app.py exits immediately, keep the window open to read the error.
echo.
echo Server stopped.
pause
