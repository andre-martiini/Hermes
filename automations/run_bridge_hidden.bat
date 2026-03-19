@echo off
cd /d "%~dp0"
:: Procura pelo executável do python no PATH
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python nao encontrado no seu sistema.
    pause
    exit /b
)
python robot_bridge.py
