@echo off
REM Encerra os servicos do Hermes iniciados em modo silencioso
REM (start_hermes_hidden.vbs), ja que suas janelas ficam ocultas
REM e nao podem ser fechadas clicando no X.

echo Encerrando servicos do Hermes...

taskkill /FI "WINDOWTITLE eq Hermes Web (Frontend)*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Hermes Automations API*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Hermes Sync (Google Tasks)*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Hermes Sync (Monitor de Paginas)*" /T /F >nul 2>&1

echo Concluido.
pause
