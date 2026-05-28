@echo off
chcp 65001 >nul
set ROOT=%~dp0
set OLLAMA=E:\ollama\ollama.exe
if not exist "%OLLAMA%" set OLLAMA=ollama

echo ===============================================================
echo  Build Smart AI Aegis (Ollama model: smart-ai-aegis)
echo  Modelfile: %ROOT%Modelfile
echo ===============================================================

"%OLLAMA%" create smart-ai-aegis -f "%ROOT%Modelfile"
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%

echo.
echo Done. Run: ollama run smart-ai-aegis
echo Or set:  set AEGIS_MODEL=smart-ai-aegis
pause
