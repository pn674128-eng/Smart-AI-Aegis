@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"
set "AEGIS_MODEL=smart-ai-aegis"

start "" /min wscript.exe //nologo "%ROOT%Start-Smart-AI-CAD-MCP.vbs"
timeout /t 2 /nobreak >nul

echo 啟動四方協作 UI ...
start "" "http://127.0.0.1:9880/"
python "%ROOT%triad_ui\triad_server.py"
