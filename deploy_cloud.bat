@echo off
REM Deploy automatizado das Firebase Cloud Functions

echo ========================================
echo   HERMES - DEPLOY CLOUD FUNCTIONS
echo ========================================
echo.

echo [1/3] Instalando dependencias...
cd functions
call npm install

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRO] Falha ao instalar dependencias
    pause
    exit /b 1
)

echo.
echo [2/3] Armazenando credenciais no Firestore...
node upload-credentials.js

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRO] Falha ao armazenar credenciais
    pause
    exit /b 1
)

cd ..

echo.
echo [3/3] Fazendo deploy das Cloud Functions...
echo Isso pode levar 2-5 minutos...
echo.
firebase deploy --only functions

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERRO] Falha no deploy
    pause
    exit /b 1
)

echo.
echo ========================================
echo   DEPLOY CONCLUIDO COM SUCESSO!
echo ========================================
echo.
echo Agora voce tem 2 Cloud Functions rodando:
echo.
echo [1] syncGoogleTasks - Dispara ao clicar em "Sync Google"
echo [2] scheduledSync - Roda automaticamente a cada 30 minutos
echo.
echo Seu sistema agora sincroniza 24/7 na nuvem!
echo Nao precisa mais deixar o computador ligado.
echo.
pause
