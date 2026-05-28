@echo off
chcp 65001 >nul
REM ============================================================
REM  Smart AI Aegis chat launcher（別名入口，同 Start-Smart-AI-Aegis.bat）
REM  位置: E:\ollama\cam-helper-tools\Cam-Helper-Chat.bat
REM    - streaming + multi-turn 對話記憶
REM    - 三種 tool_call format fallback
REM    - 直連 MCP 9877 取 Smart_AI_CAM 真實資料
REM ============================================================

setlocal

set "TOOL_DIR=%~dp0"
set "AGENT=%TOOL_DIR%agent\cam_helper_agent.py"
set "AEGIS_MODEL=smart-ai-aegis"

REM 找 Python：優先 Fusion 內建，再嘗試系統 python
set "PYTHON="

REM 1. Fusion 內建 (一定有)
for /d %%i in ("%LOCALAPPDATA%\Autodesk\webdeploy\production\*") do (
    if exist "%%i\Python\python.exe" (
        set "PYTHON=%%i\Python\python.exe"
    )
)

REM 2. 系統 Python
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
    echo  - 或安裝系統 Python: winget install Python.Python.3.13
    pause
    exit /b 1
)

echo ===============================================================
echo  Smart AI Aegis (主腦)
echo ===============================================================
echo  Python  : %PYTHON%
echo  Agent   : %AGENT%
echo  Modelfile: %TOOL_DIR%Modelfile
echo  Ollama  : http://127.0.0.1:11434
echo  MCP     : 127.0.0.1:9877
echo.
echo  指令: :help :tools :reset :stream :v :q
echo.
echo  功能:
echo   - Smart AI CAM Fusion MCP（40+ actions）
echo   - 本機學習庫 + 6 層切削（R1-R12）
echo   - CNC 縱深知識 (夾持/找正/補償/量測/流程/力學)
echo ===============================================================
echo.

"%PYTHON%" "%AGENT%"

echo.
pause
