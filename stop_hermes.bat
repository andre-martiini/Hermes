@echo off
echo Finalizando servicos do Hermes (Frontend, Sincronizador e Automacoes)...
echo.

REM 1. Para o Frontend na porta 5173
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173 ^| findstr LISTENING') do (
    echo Parando frontend (PID: %%a)...
    taskkill /f /pid %%a >nul 2>nul
)

REM 2. Para as Automações na porta 8000
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    echo Parando automacoes (PID: %%a)...
    taskkill /f /pid %%a >nul 2>nul
)

REM 3. Para o sincronizador Google Tasks (hermes_cli.py)
echo Parando sincronizador Google Tasks...
wmic process where "commandline like '%%hermes_cli.py%%'" call terminate >nul 2>nul

echo.
echo ✅ Todos os servicos do Hermes foram finalizados!
echo.
pause
