@echo off
REM ============================================================
REM  Smart_AI_CAM cam-helper chat launcher
REM  雙擊此檔開啟 cam-helper Agent REPL（streaming + 多輪 + tool call）
REM
REM  前提:
REM    1. Ollama 已在 127.0.0.1:11434 運行
REM    2. (可選) Fusion 360 + Smart_AI_CAM 已載入，MCP 9877
REM ============================================================

setlocal

set "SCRIPT_DIR=%~dp0"
set "AGENT=%SCRIPT_DIR%scripts\cam_helper_agent.py"

REM 找 Python：優先用 Fusion 內建 (一定有)，再嘗試系統 python
set "PYTHON="

REM 1. Fusion 內建
for /d %%i in ("%LOCALAPPDATA%\Autodesk\webdeploy\production\*") do (
    if exist "%%i\Python\python.exe" (
        set "PYTHON=%%i\Python\python.exe"
    )
)

REM 2. 系統 Python (如果有)
if "%PYTHON%"=="" (
    where python.exe 2>nul | findstr /v "WindowsApps" >nul
    if %ERRORLEVEL%==0 (
        for /f "delims=" %%p in ('where python.exe ^| findstr /v "WindowsApps"') do (
            set "PYTHON=%%p"
            goto :found
        )
    )
)

:found
if "%PYTHON%"=="" (
    echo [ERROR] 找不到 Python.exe
    echo  - 請檢查 Fusion 360 是否裝在預設位置
    echo  - 或安裝系統 Python ^(winget install Python.Python.3.13^)
    pause
    exit /b 1
)

echo ===============================================================
echo  Smart_AI_CAM cam-helper Agent v2
echo ===============================================================
echo  Python: %PYTHON%
echo  Agent : %AGENT%
echo  Ollama: http://127.0.0.1:11434
echo  MCP   : 127.0.0.1:9877
echo.
echo  指令: :help :tools :reset :stream :v :q
echo ===============================================================
echo.

"%PYTHON%" "%AGENT%"

echo.
pause
