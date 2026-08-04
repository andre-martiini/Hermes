@echo off
cd /d "%~dp0"
echo Iniciando Hermes Voice Client (Porta 8765)...
start "Hermes Voice Server" /min .venv\Scripts\python.exe -m uvicorn main:app --port 8765
timeout /t 2 /nobreak >nul
start "" http://localhost:8765
