@echo off
echo Starting Roulette Server...
cd /d %~dp0
python comment_dart.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Server crashed or failed to start.
    echo Please check the error message above.
    pause
)
pause
