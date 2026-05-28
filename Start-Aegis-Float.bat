@echo off
REM 轉交 VBS，避免留下黑色命令列視窗（可安全關閉本視窗）
wscript //nologo "%~dp0Start-Aegis-Float.vbs"
exit /b 0
