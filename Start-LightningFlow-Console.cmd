@echo off
setlocal
set PYTHONUTF8=1
cd /d "%~dp0"
".venv\Scripts\python.exe" -m lightningflow run %*
if errorlevel 1 pause
