@echo off
setlocal
chcp 65001 >nul

set "SCRIPT_DIR=%~dp0"
set "BACKEND_DIR=%SCRIPT_DIR%backend"
set "FRONTEND_DIR=%SCRIPT_DIR%frontend"

echo ============================================================
echo AMSRAG Web One-Click Launcher
echo ============================================================
echo.

if not exist "%BACKEND_DIR%\start.bat" (
    echo [ERROR] Backend launcher not found: %BACKEND_DIR%\start.bat
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\start.bat" (
    echo [ERROR] Frontend launcher not found: %FRONTEND_DIR%\start.bat
    pause
    exit /b 1
)

echo [1/2] Starting backend service...
start "AMSRAG Backend" cmd /k "cd /d ""%BACKEND_DIR%"" && call start.bat"

set "BACKEND_HEALTH_URL=http://127.0.0.1:8000/health"
set /a BACKEND_WAIT_SECONDS=120
set /a BACKEND_ELAPSED=0
echo Waiting backend health check: %BACKEND_HEALTH_URL%

:wait_backend
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%BACKEND_HEALTH_URL%' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 goto backend_ready
if %BACKEND_ELAPSED% GEQ %BACKEND_WAIT_SECONDS% goto backend_timeout
timeout /t 2 /nobreak >nul
set /a BACKEND_ELAPSED+=2
goto wait_backend

:backend_ready
echo [OK] Backend is ready.
goto start_frontend

:backend_timeout
echo [WARN] Backend not ready within %BACKEND_WAIT_SECONDS%s.
echo [WARN] Frontend will still start, but API requests may fail until backend is up.

:start_frontend
echo [2/2] Starting frontend service...
start "AMSRAG Frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && call start.bat"

echo.
echo ============================================================
echo Launch complete
echo ============================================================
echo Frontend : http://127.0.0.1:5173
echo Backend  : http://127.0.0.1:8000
echo API Docs : http://127.0.0.1:8000/docs
echo.
echo Close the backend/frontend terminal windows to stop services.
echo.
pause
