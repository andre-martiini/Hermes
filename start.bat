@echo off
REM Hermes - Inicializador Completo (uso manual, com janelas visiveis)
REM Inicia o frontend, sincronizacao e servicos de voz automaticamente

echo ========================================
echo   HERMES - SISTEMA DE GESTAO
echo ========================================
echo.
echo Iniciando servicos...
echo.

REM Inicia o servidor web em uma nova janela
start "Hermes Web (Frontend)" cmd /k "npm run dev"

REM Aguarda 2 segundos
timeout /t 2 /nobreak >nul

REM Inicia a API local que aciona as automacoes Selenium
start "Hermes Automations API" cmd /k "cd /d %~dp0automations && python server.py"

REM A sincronizacao principal roda na Cloud Function. Nao inicie tambem
REM hermes_cli.py watch: seriam dois consumidores do mesmo system/sync.

REM Inicia o monitor de paginas web em outra janela
start "Hermes Sync (Monitor de Paginas)" cmd /k "python hermes_cli.py watch-pages"

REM Inicia o Hermes Voice Bridge (Gemini Live - porta 3002)
start "Hermes Voice Bridge" cmd /k "cd /d %~dp0hermes-voice-bridge && .venv\Scripts\python.exe -m uvicorn main:app --port 3002"

REM Inicia o Hermes Voice Client (STT/TTS Local + MCP - porta 8765)
start "Hermes Voice Client" cmd /k "cd /d %~dp0hermes-voice-client && .venv\Scripts\python.exe -m uvicorn main:app --port 8765"

echo.
echo ========================================
echo   SERVICOS INICIADOS!
echo ========================================
echo.
echo [1] Hermes Web: http://localhost:5173
echo [2] Hermes Automations API: http://127.0.0.1:8000
echo [3] Hermes Sync: Cloud Function
echo [4] Hermes Monitor: Verificando paginas web
echo [5] Hermes Voice Bridge: http://127.0.0.1:3002
echo [6] Hermes Voice Client: http://127.0.0.1:8765
echo.
echo Feche esta janela quando terminar.
echo Para parar os servicos, feche as outras janelas.
echo.
pause
