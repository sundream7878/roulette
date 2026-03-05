@echo off
echo Installing required libraries...
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Installation failed.
    pause
    exit /b %ERRORLEVEL%
)
echo.
echo Libraries installed successfully!
pause
