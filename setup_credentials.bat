@echo off
REM Script para renovar credenciais do Google usadas pelo Hermes

echo ========================================
echo   RENOVACAO DE CREDENCIAIS GOOGLE
echo ========================================
echo.

cd functions
python setup_credentials.py --force

pause

