@echo off
title Smart AI Aegis Web UI
color 0B

echo.
echo ==============================================================
echo   Smart AI Aegis Web UI
echo ==============================================================
echo.

REM ---- Find Fusion Python ----
set "PY="
for /d %%i in ("%LOCALAPPDATA%\Autodesk\webdeploy\production\*") do (
    if exist "%%i\Python\python.exe" set "PY=%%i\Python\python.exe"
)

if "%PY%"=="" (
    echo [ERROR] Fusion Python not found.
    echo Looked in: %LOCALAPPDATA%\Autodesk\webdeploy\production\*\Python\python.exe
    echo.
    pause
    exit /b 1
)

set "SRV=%~dp0server.py"
set "URL=http://127.0.0.1:8000"

echo   Python : %PY%
echo   Server : %SRV%
echo   URL    : %URL%
echo.

REM ---- Check server.py exists ----
if not exist "%SRV%" (
    echo [ERROR] server.py not found at: %SRV%
    echo.
    pause
    exit /b 1
)

REM ---- Schedule browser open in 4 seconds ----
echo   Browser will open in 4 seconds...
echo.
start "" /b cmd /c "ping -n 5 127.0.0.1 >nul & start %URL%"

echo ==============================================================
echo   Starting server. Press Ctrl+C in this window to stop.
echo ==============================================================
echo.

"%PY%" "%SRV%"

echo.
echo ==============================================================
echo   Server stopped. Press any key to close this window.
echo ==============================================================
pause >nul
