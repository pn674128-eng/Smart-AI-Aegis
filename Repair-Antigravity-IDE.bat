@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"

echo Running Antigravity IDE repair...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%Repair-Antigravity-IDE.ps1"

echo.
echo Done. If Antigravity still crashes, reinstall Antigravity IDE and run this again.
pause
