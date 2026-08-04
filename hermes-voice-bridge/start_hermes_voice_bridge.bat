@echo off
cd /d "%~dp0"
echo Iniciando Hermes Voice Bridge (Porta 3002)...
.venv\Scripts\python.exe -m uvicorn main:app --port 3002
pause
