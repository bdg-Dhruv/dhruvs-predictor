@echo off
setlocal
cd /d "%~dp0"

echo ============================================
echo  Signal Desk - Reset
echo ============================================
echo.

echo Clearing Python bytecode cache...
if exist "__pycache__" (
    rmdir /s /q "__pycache__"
    echo    Removed __pycache__
) else (
    echo    No cache found - nothing to clear.
)

echo.
echo Note: since API keys are now entered on the login page instead of
echo .env, there's nothing else to reset locally. If you were logged in
echo and something looks stuck, just restart the server (run.bat) - that
echo clears every signed-in session.
echo.
pause
