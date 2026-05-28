@echo off
chcp 65001 >nul
set ROOT=%~dp0
cd /d "%ROOT%"
for %%P in ("%LOCALAPPDATA%\Autodesk\webdeploy\production\*\Python\python.exe") do set PY=%%P
if not defined PY set PY=python
"%PY%" "%ROOT%tools\sync_knowledge_mirror.py"
pause
