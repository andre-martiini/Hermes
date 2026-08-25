@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_task.ps1"
if errorlevel 1 (
  echo.
  echo A instalacao nao foi concluida. Revise a mensagem acima.
  pause
  exit /b 1
)
pause
