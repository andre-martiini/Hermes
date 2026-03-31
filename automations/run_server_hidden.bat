@echo off
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python nao encontrado no seu sistema.
    pause
    exit /b
)
python -m uvicorn server:app --host 127.0.0.1 --port 8000
