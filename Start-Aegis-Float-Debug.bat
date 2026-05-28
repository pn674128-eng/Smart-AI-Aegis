@echo off
setlocal
set "APP=E:\ollama\cam-helper-tools\aegis_float\aegis_float_app.py"
set "AEGIS_MODEL=smart-ai-aegis"
python "%APP%"
echo.
echo [Aegis Float exited. Press any key]
pause >nul
