@echo off
echo Finalizando processos do Robô Hermes...
taskkill /f /im python.exe /fi "WINDOWTITLE eq robot_bridge.py*" >nul 2>nul
taskkill /f /im python.exe /fi "WINDOWTITLE eq emissor_nfse.py*" >nul 2>nul
:: Como rodam escondidos sem titulo, o jeito mais seguro se nao houver outros pythons:
:: taskkill /f /im python.exe
echo.
echo ✅ Robô e Automações finalizados com sucesso!
pause
