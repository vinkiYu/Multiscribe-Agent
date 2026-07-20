@echo off
setlocal

rem One-click launcher for Multiscribe-Agent on Windows.
set "PROJECT_ROOT=F:\software\Multiscribe\MultiscribeAgent-main"
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "URL=http://127.0.0.1:8000"

title Multiscribe-Agent
cd /d "%PROJECT_ROOT%"
if errorlevel 1 (
    echo [ERROR] Project directory not found: %PROJECT_ROOT%
    pause
    exit /b 1
)

if not exist "%PYTHON%" (
    echo [ERROR] Python environment not found: %PYTHON%
    echo Create the project environment first, for example: uv sync --extra dev --extra text
    pause
    exit /b 1
)

if not exist ".env" (
    echo [WARN] .env is missing. Copy .env.example to .env and add your API keys/webhooks.
)

rem The backend serves frontend/dist when the production bundle exists.
set "NEEDS_FRONTEND_BUILD="
if not exist "frontend\dist\index.html" set "NEEDS_FRONTEND_BUILD=1"
if not exist "frontend\dist\assets" set "NEEDS_FRONTEND_BUILD=1"
if defined NEEDS_FRONTEND_BUILD (
    where npm >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] frontend\dist is missing and npm is not available.
        echo Install Node.js, then run npm install and npm run build in frontend\.
        pause
        exit /b 1
    )
    echo [INFO] Frontend build not found. Building it now...
    if not exist "frontend\node_modules" (
        pushd frontend
        call npm install
        if errorlevel 1 (
            popd
            echo [ERROR] npm install failed.
            pause
            exit /b 1
        )
        popd
    )
    pushd frontend
    call npm run build
    if errorlevel 1 (
        popd
        echo [ERROR] Frontend build failed.
        pause
        exit /b 1
    )
    popd
)

rem Open the browser only after the health endpoint responds.
start "" /b powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(30); do { try { $response=Invoke-WebRequest -UseBasicParsing -Uri '%URL%/healthz' -TimeoutSec 1; if ($response.StatusCode -eq 200) { Start-Process '%URL%'; exit 0 } } catch {}; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $deadline); Start-Process '%URL%'"

echo [INFO] Starting Multiscribe-Agent at %URL%
echo [INFO] Close this window to stop the service.
"%PYTHON%" -m multiscribe_agent serve --host 127.0.0.1 --port 8000

echo.
echo [INFO] Multiscribe-Agent stopped.
pause
