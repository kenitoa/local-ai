@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-local-ai.ps1"
if errorlevel 1 (
  echo.
  echo Local AI failed to start. Check publish\logs for details.
  pause
)
