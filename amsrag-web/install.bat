@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cls

echo ============================================================
echo AMSRAG Web Dependency Installer
echo ============================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "BACKEND_DIR=%SCRIPT_DIR%backend"
set "FRONTEND_DIR=%SCRIPT_DIR%frontend"

echo [1/4] Checking Python and pip...
python --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)
python -m pip --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] pip is not available in current Python environment.
    pause
    exit /b 1
)
echo [OK] Python and pip detected.
echo.

echo [2/4] Installing backend dependencies...
pushd "%BACKEND_DIR%"
python -m pip install -r requirements.txt
if errorlevel 1 (
    popd
    echo [ERROR] Backend dependency installation failed.
    pause
    exit /b 1
)
popd
echo [OK] Backend dependencies installed.
echo.

echo [3/4] Checking Node.js and npm...
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

echo [4/4] Installing frontend dependencies...
pushd "%FRONTEND_DIR%"
call npm install
if errorlevel 1 (
    popd
    echo [ERROR] Frontend dependency installation failed.
    pause
    exit /b 1
)
popd
echo [OK] Frontend dependencies installed.
echo.

echo ============================================================
echo Installation complete
echo ============================================================
echo Next step:
echo   quick-start.bat
echo or
echo   start-all.bat
echo.
pause
