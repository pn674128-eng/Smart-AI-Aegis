@echo off
chcp 65001 >nul
setlocal
echo 請把 Antigravity 的 .exe 完整路徑貼上（或拖曳檔案到此視窗）：
set /p AG_PATH=
if not exist "%AG_PATH%" (
  echo 找不到檔案: %AG_PATH%
  pause
  exit /b 1
)
setx ANTIGRAVITY_EXE "%AG_PATH%"
echo.
echo 已設定 ANTIGRAVITY_EXE
echo 重新開啟 Ollama / REPL 後，「開始AI協作」會嘗試自動開啟 Antigravity。
pause
