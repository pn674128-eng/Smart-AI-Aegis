@echo off
chcp 65001 >nul
setlocal
set "TOOL_DIR=%~dp0"
set "MCP=%TOOL_DIR%Smart AI CAD\mcp\cad_mcp_server.py"
python "%MCP%"
pause
