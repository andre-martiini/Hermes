@echo off
cd /d "%~dp0"

where uv >nul 2>nul
if %errorlevel% equ 0 (
    echo [INFO] Iniciando com UV...
    uv run python robot_bridge.py
    exit /b
)

:: Procura pelo executável do python no PATH
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python ou UV nao encontrados no seu sistema.
    pause
    exit /b
)
python robot_bridge.py

