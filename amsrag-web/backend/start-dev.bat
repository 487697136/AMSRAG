@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
pushd "%~dp0"

for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
set "PYTHONPATH=%PROJECT_ROOT%;%PYTHONPATH%"
set "TARGET_PORT=8000"

echo ============================================================
echo AMSRAG Web Backend Dev Launcher
 echo ============================================================
echo Project root: %PROJECT_ROOT%
echo.

set "CONDA_PATH="
for %%D in (E D C) do (
    if exist "%%D:\Anaconda3\Scripts\activate.bat" (
        set "CONDA_PATH=%%D:\Anaconda3"
        goto :activate_conda
    )
)
if exist "%USERPROFILE%\Anaconda3\Scripts\activate.bat" (
    set "CONDA_PATH=%USERPROFILE%\Anaconda3"
)

:activate_conda
if defined CONDA_PATH (
    echo [1/6] Activating conda environment: pytorch_new
    call "%CONDA_PATH%\Scripts\activate.bat" pytorch_new >nul 2>nul
    if /I "!CONDA_DEFAULT_ENV!"=="pytorch_new" (
        echo [OK] Conda environment activated.
    ) else (
        echo [WARN] Failed to activate pytorch_new. Continue with current Python.
    )
) else (
    echo [WARN] Anaconda not found. Continue with current Python.
)
echo.

echo [2/6] Checking Python availability...
python --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not available in PATH.
    pause
    exit /b 1
)
echo [OK] Python detected.
echo.

echo [3/6] Checking project layout...
if not exist "%PROJECT_ROOT%\amsrag\__init__.py" (
    echo [ERROR] amsrag package not found under project root.
    echo Expected path: %PROJECT_ROOT%\amsrag\__init__.py
    pause
    exit /b 1
)
echo [OK] Project layout looks valid.
echo.

echo [4/6] Checking backend dependencies...
python -c "import importlib,sys;mods=['fastapi','uvicorn','sqlalchemy','loguru','jose','passlib','pydantic_settings','neo4j'];missing=[m for m in mods if importlib.util.find_spec(m) is None];print('missing: '+', '.join(missing)) if missing else None;sys.exit(1 if missing else 0)" >nul 2>nul
if errorlevel 1 (
    echo [INFO] Missing dependencies detected. Installing from requirements.txt...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install backend dependencies.
        pause
        exit /b 1
    )
    echo [OK] Backend dependencies installed.
) else (
    echo [OK] Backend dependencies are ready.
)
echo.

echo [5/6] Checking port availability...
set "PORT_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%TARGET_PORT% .*LISTENING"') do (
    set "PORT_PID=%%P"
    goto :port_busy
)
echo [OK] Port %TARGET_PORT% is available.
goto :start_server

:port_busy
echo [ERROR] Port %TARGET_PORT% is already in use by PID !PORT_PID!.
echo [ERROR] Stop the existing backend process before using dev reload mode.
pause
exit /b 1

:start_server
echo.
echo [6/6] Starting FastAPI service in reload mode...
echo Backend URL: http://127.0.0.1:%TARGET_PORT%
echo API Docs  : http://127.0.0.1:%TARGET_PORT%/docs
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port %TARGET_PORT% --reload
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%