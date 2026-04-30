@echo off
REM Script para renovar credenciais do Google usadas pelo Hermes

echo ========================================
echo   RENOVACAO DE CREDENCIAIS GOOGLE
echo ========================================
echo.

pushd "%~dp0functions"
if errorlevel 1 (
    echo Nao foi possivel acessar a pasta functions.
    pause
    exit /b 1
)

python setup_credentials.py --force
set "EXIT_CODE=%ERRORLEVEL%"

popd

pause
exit /b %EXIT_CODE%

