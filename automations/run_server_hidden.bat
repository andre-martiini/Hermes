@echo off
cd /d "%~dp0"

where uv >nul 2>nul
if %errorlevel% equ 0 (
    echo [INFO] Iniciando com UV...
    uv run uvicorn server:app --host 127.0.0.1 --port 8000
    exit /b
)

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python ou UV nao encontrados no seu sistema.
    pause
    exit /b
)
python -m uvicorn server:app --host 127.0.0.1 --port 8000

