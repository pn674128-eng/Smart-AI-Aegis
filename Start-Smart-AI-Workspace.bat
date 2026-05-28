@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"

REM 一鍵：CAD 協作端口（背景）+ 提示只用 Ollama 與 Aegis 對話
start "" /min wscript.exe //nologo "%ROOT%Start-Smart-AI-CAD-MCP.vbs"

echo.
echo ========================================
echo  Smart AI 工作區已啟動（背景服務）
echo ========================================
echo   CAD 協作 MCP :9876  （已嘗試背景啟動）
echo.
echo   師父日常只需一個對話入口：
echo     - Ollama 選 smart-ai-aegis
echo     或  Start-Smart-AI-Aegis.bat
echo.
echo   不必為了協作單切換 Cursor。
echo   只有要改程式時，打開本資料夾的 Cursor 即可。
echo.
echo   收件匣: store\inbox\LATEST_FOR_CURSOR.md
echo ========================================
echo.
pause
