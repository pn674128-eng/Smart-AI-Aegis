@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"
set "PYEXE="
if exist "%ROOT%.venv-bridge312\Scripts\python.exe" set "PYEXE=%ROOT%.venv-bridge312\Scripts\python.exe"
if not defined PYEXE if exist "%ROOT%.venv-bridge\Scripts\python.exe" set "PYEXE=%ROOT%.venv-bridge\Scripts\python.exe"
if not defined PYEXE set "PYEXE=python"

if "%~1"=="" (
  echo 用法:
  echo   Run-Local-AI-Bridge.bat "工作區路徑" "協同修改任務描述"
  echo.
  echo 範例:
  echo   Run-Local-AI-Bridge.bat "%ROOT%Smart_AI_CAM_Tools" "把 XXX 接到 cutting_resolver"
  echo.
  echo 環境變數（可選）:
  echo   CURSOR_API_KEY     — Cursor SDK 實作輪
  echo   GEMINI_API_KEY     — Antigravity SDK 探索輪
  echo   BRIDGE_CURSOR_MODE — sdk ^| ollama （預設 sdk）
  echo   BRIDGE_AG_MODE     — sdk ^| ollama （預設 sdk）
  exit /b 1
)

if "%~2"=="" (
  echo 請提供第二參數：任務描述
  exit /b 1
)

if not defined CURSOR_API_KEY (
  echo [提示] 未設定 CURSOR_API_KEY，實作輪將使用 Ollama 備援且不會自動改檔。
  echo        請先: set CURSOR_API_KEY=你的新金鑰
  echo.
)

start "" /min wscript.exe //nologo "%ROOT%Start-Smart-AI-CAD-MCP.vbs"
timeout /t 2 /nobreak >nul

"%PYEXE%" -m bridge.diagnose
echo.
"%PYEXE%" -m bridge run --workspace "%~1" --task "%~2"
exit /b %ERRORLEVEL%
