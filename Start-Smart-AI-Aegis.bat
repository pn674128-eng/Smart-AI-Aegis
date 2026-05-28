@echo off
chcp 65001 >nul
setlocal
set "TOOL_DIR=%~dp0"
set "AGENT=%TOOL_DIR%agent\cam_helper_agent.py"
set "AEGIS_MODEL=smart-ai-aegis"

for /d %%i in ("%LOCALAPPDATA%\Autodesk\webdeploy\production\*") do (
    if exist "%%i\Python\python.exe" set "PYTHON=%%i\Python\python.exe"
)
if not defined PYTHON set PYTHON=python

echo ===============================================================
echo  Smart AI Aegis — 值得信任的智能體
echo  Model: %AEGIS_MODEL%  ^|  MCP 9877 Smart AI CAM Fusion
echo ===============================================================
echo.

"%PYTHON%" "%AGENT%"
pause
