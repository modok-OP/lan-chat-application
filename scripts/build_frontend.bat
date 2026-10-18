@echo off
echo ===================================================
echo Building Frontend SPA for Single-Origin LAN Hosting
echo ===================================================

cd /d "%~dp0\..\frontend"

echo [INFO] Running npm run build...
call npm.cmd run build

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Frontend bundle created in frontend\dist\
    echo When FastAPI runs, it will serve this build directly at http://^<host-ip^>:8000
) else (
    echo [ERROR] Frontend build failed.
)

pause
