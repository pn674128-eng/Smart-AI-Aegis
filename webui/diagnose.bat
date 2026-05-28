@echo off
REM ============================================================
REM  診斷工具 - 雙擊看 Web UI 環境哪裡有問題
REM ============================================================

title Diagnose
color 0E

echo.
echo ============== Web UI 環境診斷 ==============
echo.

echo [1] 尋找 Fusion Python...
set "PY="
for /d %%i in ("%LOCALAPPDATA%\Autodesk\webdeploy\production\*") do (
    if exist "%%i\Python\python.exe" (
        set "PY=%%i\Python\python.exe"
        echo     Found: %%i\Python\python.exe
    )
)

if "%PY%"=="" (
    echo     ✗ NOT FOUND
) else (
    echo     ✓ OK
)
echo.

echo [2] Python version...
if not "%PY%"=="" (
    "%PY%" --version
)
echo.

echo [3] 檢查 server.py...
set "SRV=%~dp0server.py"
if exist "%SRV%" (
    echo     ✓ %SRV%
) else (
    echo     ✗ NOT FOUND: %SRV%
)
echo.

echo [4] 檢查 cam_helper_agent.py...
set "AGENT=%~dp0..\agent\cam_helper_agent.py"
if exist "%AGENT%" (
    echo     ✓ %AGENT%
) else (
    echo     ✗ NOT FOUND: %AGENT%
)
echo.

echo [5] 檢查 8000 port 是否被佔用...
netstat -ano | findstr ":8000" | findstr "LISTENING"
if %ERRORLEVEL%==0 (
    echo     ✗ 8000 已被某個進程佔用
) else (
    echo     ✓ 8000 free
)
echo.

echo [6] Ollama 在跑?
curl -s -o nul -w "    HTTP %%{http_code}" http://127.0.0.1:11434/api/tags
echo.
echo.

echo [7] MCP 9877 在跑?
powershell -NoProfile -Command "try { (New-Object Net.Sockets.TcpClient('127.0.0.1', 9877)).Close(); 'MCP alive' } catch { 'MCP offline' }"
echo.

echo [8] 試啟動 server.py 一秒看 stderr...
if not "%PY%"=="" (
    if exist "%SRV%" (
        timeout /t 1 /nobreak >nul
        "%PY%" -c "import sys; sys.path.insert(0, r'%~dp0..\agent'); import cam_helper_agent; print('  cam_helper_agent OK, model=' + cam_helper_agent.MODEL)"
    )
)
echo.

echo ============== 診斷結束 ==============
echo.
pause
