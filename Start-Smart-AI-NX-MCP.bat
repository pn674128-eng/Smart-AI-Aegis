@echo off
REM Smart AI CAM-NX MCP only (port 9878)
cd /d "%~dp0"
title Smart AI CAM-NX MCP 9878
set PY=%LOCALAPPDATA%\Autodesk\webdeploy\production\4bca736941837d3e42bba21bb36b9891e34b2fce\Python\python.exe
if not exist "%PY%" set PY=python
echo Starting MCP on 127.0.0.1:9878 ...
"%PY%" -m smart_ai_nx.mcp_server
pause
