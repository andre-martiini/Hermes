@echo off
cd /d "%~dp0"

REM Detecta se o uv está instalado no sistema
where uv >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_CMD=uv run python
    set UVICORN_CMD=uv run uvicorn
) else (
    set PYTHON_CMD=python
    set UVICORN_CMD=python -m uvicorn
)

REM Inicia o frontend (Vite) em background sem abrir janela
start /B "" npm run dev

REM Inicia o sincronizador Google Tasks em background sem abrir janela
start /B "" %PYTHON_CMD% hermes_cli.py watch

REM Inicia o servidor de automações (FastAPI) em background sem abrir janela
cd automations
start /B "" %UVICORN_CMD% server:app --host 127.0.0.1 --port 8000
