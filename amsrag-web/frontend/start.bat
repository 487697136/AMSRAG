@echo off
setlocal
chcp 65001 >nul
pushd "%~dp0"

echo ========================================
echo AMSRAG Web Frontend Launcher
echo ========================================
echo.

echo [1/3] Checking Node.js and npm...
node --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js is not installed or not in PATH.
    pause
    exit /b 1
)
call npm --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm is not available.
    pause
    exit /b 1
)
echo [OK] Node.js and npm detected.
echo.

echo [2/3] Checking frontend dependencies...
if not exist "node_modules" (
    echo [INFO] node_modules not found. Installing dependencies...
    call npm install
    if errorlevel 1 (
        echo [ERROR] Failed to install frontend dependencies.
        pause
        exit /b 1
    )
    echo [OK] Frontend dependencies installed.
) else (
    echo [OK] Frontend dependencies are ready.
)
echo.

echo [3/3] Starting Vite dev server...
echo Frontend URL: http://127.0.0.1:5173
echo.
call npm run dev
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
