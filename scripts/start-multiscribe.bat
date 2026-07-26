@echo off
setlocal

set "PROJECT_DIR=F:\software\Multiscribe\MultiscribeAgent-main"
set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "NPM_EXE=npm.cmd"

if not exist "%PYTHON_EXE%" (
  echo Python virtual environment was not found:
  echo %PYTHON_EXE%
  pause
  exit /b 1
)

pushd "%PROJECT_DIR%"

netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul
if errorlevel 1 (
  start "Multiscribe Backend" cmd /k "cd /d %PROJECT_DIR% && %PYTHON_EXE% -m multiscribe_agent serve --host 127.0.0.1 --port 8000"
) else (
  echo Backend is already listening on http://127.0.0.1:8000
)

netstat -ano | findstr /r /c:":5173 .*LISTENING" >nul
if errorlevel 1 (
  start "Multiscribe Frontend" cmd /k "cd /d %PROJECT_DIR%\frontend && %NPM_EXE% run dev -- --host 127.0.0.1 --port 5173"
) else (
  echo Frontend is already listening on http://127.0.0.1:5173
)

popd
echo.
echo Multiscribe is starting.
echo Console: http://127.0.0.1:5173/console.html
echo Backend: http://127.0.0.1:8000
pause
