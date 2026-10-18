@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo Starting LAN Chat Application Server (Backend)
echo ===================================================

cd /d "%~dp0\.."

if not exist "backend\.venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at backend\.venv
    echo Run the following commands to create it:
    echo   python -m venv backend\.venv
    echo   backend\.venv\Scripts\python -m pip install -r backend\requirements.txt
    exit /b 1
)

echo [INFO] Activating virtual environment...
call backend\.venv\Scripts\activate.bat

echo [INFO] Discovering local IPv4 addresses for LAN access:
for /f "tokens=4" %%a in ('route print ^| findstr 0.0.0.0.*0.0.0.0') do (
    echo [LAN TIP] Possible Host IP: %%a
)
echo Run "ipconfig" in Command Prompt for full network adapter details.
echo.
echo [INFO] Launching Uvicorn server on http://0.0.0.0:8000 ...
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

pause
