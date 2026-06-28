@echo off
REM Hermes - Inicializador Completo
REM Inicia o frontend e a sincronização automaticamente

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
echo [2] Hermes Sync: Monitorando sincronizacao
echo [3] Hermes Monitor: Verificando paginas web
echo.
echo Feche esta janela quando terminar.
echo Para parar os servicos, feche as outras 2 janelas.
echo.
pause
