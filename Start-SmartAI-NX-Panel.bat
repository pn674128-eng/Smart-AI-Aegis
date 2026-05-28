@echo off
REM Smart AI CAM-NX side panel (Smart AI CAM trunk UI, V8.702 data ref)
cd /d "%~dp0"
title Smart AI NX Panel 9879
set PY=%LOCALAPPDATA%\Autodesk\webdeploy\production\4bca736941837d3e42bba21bb36b9891e34b2fce\Python\python.exe
if not exist "%PY%" set PY=python
echo Ensure MCP 9878 is running (Start-Smart-AI-NX-MCP.bat)
echo Panel: http://127.0.0.1:9879/
start "" "http://127.0.0.1:9879/"
"%PY%" -m smart_ai_nx.ui.panel_server
pause
