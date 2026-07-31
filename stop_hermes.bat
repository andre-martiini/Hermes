@echo off
REM Encerra os servicos do Hermes iniciados em modo silencioso
REM (start_hidden.vbs), ja que suas janelas ficam ocultas e nao
REM podem ser fechadas clicando no X. Os logs de cada servico
REM ficam em .\logs\ caso precise investigar antes de encerrar.

echo Encerrando servicos do Hermes...

taskkill /FI "WINDOWTITLE eq Hermes Web (Frontend)*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Hermes Automations API*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Hermes Sync (Google Tasks)*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Hermes Sync (Monitor de Paginas)*" /T /F >nul 2>&1

echo Concluido.
pause
