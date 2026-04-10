@echo off
echo Starting Commission Calculator...

echo Stopping any running instance on port 8050...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8050 "') do (
    taskkill /PID %%a /F >nul 2>&1
)

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.12+
    pause
    exit /b 1
)

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt --quiet

echo.
echo Launching Commission Calculator at http://localhost:8050
python dev.py %*
