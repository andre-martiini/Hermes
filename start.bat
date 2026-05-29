@echo off
REM Hermes - Inicializador Completo
REM Inicia o frontend, a sincronização e o servidor de automação automaticamente

echo ========================================
echo   HERMES - SISTEMA DE GESTAO
echo ========================================
echo.
echo Iniciando servicos...
echo.

REM Detecta se o uv está instalado no sistema
where uv >nul 2>nul
if %errorlevel% equ 0 (
    echo [INFO] UV detectado! Usando UV para executar os scripts Python de forma mais confiavel.
    set PYTHON_CMD=uv run python
    set UVICORN_CMD=uv run uvicorn
) else (
    echo [INFO] UV nao encontrado. Usando comando Python padrão do sistema.
    set PYTHON_CMD=python
    set UVICORN_CMD=python -m uvicorn
)

REM Inicia o servidor web em uma nova janela
start "Hermes Web (Frontend)" cmd /k "npm run dev"

REM Aguarda 2 segundos
timeout /t 2 /nobreak >nul

REM Inicia o sincronizador em outra janela
start "Hermes Sync (Google Tasks)" cmd /k "%PYTHON_CMD% hermes_cli.py watch"

REM Aguarda 1 segundo
timeout /t 1 /nobreak >nul

REM Inicia o servidor de automação em outra janela
start "Hermes Automations (FastAPI)" cmd /k "cd automations && %UVICORN_CMD% server:app --host 127.0.0.1 --port 8000"

echo.
echo ========================================
echo   SERVICOS INICIADOS!
echo ========================================
echo.
echo [1] Hermes Web: http://localhost:5173
echo [2] Hermes Sync: Monitorando sincronizacao
echo [3] Hermes Automations: Servidor FastAPI na porta 8000
echo.
echo Feche esta janela quando terminar.
echo Para parar os servicos, feche as outras 3 janelas.
echo.
pause
