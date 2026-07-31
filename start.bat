@echo off
REM Hermes - Inicializador Completo (uso manual, com janelas visiveis)
REM Inicia o frontend e a sincronização automaticamente
REM
REM Para inicializacao AUTOMATICA e SILENCIOSA (sem janelas), o Windows usa
REM start_hidden.vbs via atalho na pasta Startup - nao apague esse arquivo
REM achando que e "codigo morto" so porque nada no repo o referencia.

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

REM Inicia o sincronizador em outra janela
start "Hermes Sync (Google Tasks)" cmd /k "python hermes_cli.py watch"

REM Inicia o monitor de paginas web em outra janela
start "Hermes Sync (Monitor de Paginas)" cmd /k "python hermes_cli.py watch-pages"

echo.
echo ========================================
echo   SERVICOS INICIADOS!
echo ========================================
echo.
echo [1] Hermes Web: http://localhost:5173
echo [2] Hermes Automations API: http://127.0.0.1:8000
echo [3] Hermes Sync: Monitorando sincronizacao
echo [4] Hermes Monitor: Verificando paginas web
echo.
echo Feche esta janela quando terminar.
echo Para parar os servicos, feche as outras 2 janelas.
echo.
pause
