@echo off
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python nao encontrado no PATH.
    pause
    exit /b
)
python queue_processor.py
