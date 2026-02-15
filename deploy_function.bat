@echo off
REM Script de deploy automatizado da Cloud Function Hermes Sync

echo ========================================
echo   HERMES SYNC - DEPLOY CLOUD FUNCTION
echo ========================================
echo.

REM Verifica se gcloud está instalado
where gcloud >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Google Cloud CLI nao encontrado!
    echo Por favor, instale: https://cloud.google.com/sdk/docs/install
    pause
    exit /b 1
)

echo [1/4] Verificando autenticacao...
gcloud auth list

echo.
echo [2/4] Configurando projeto...
set /p PROJECT_ID="Digite o ID do seu projeto Firebase: "
gcloud config set project %PROJECT_ID%

echo.
echo [3/4] Habilitando APIs necessarias...
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable firestore.googleapis.com

echo.
echo [4/4] Fazendo deploy da Cloud Function...
cd functions
gcloud functions deploy hermes-sync --gen2 --runtime=python311 --region=us-central1 --source=. --entry-point=on_sync_request --trigger-event-filters="type=google.cloud.firestore.document.v1.written" --trigger-event-filters="database=(default)" --trigger-location=us-central1 --trigger-event-filters-path-pattern="document=system/sync"

echo.
echo ========================================
echo   DEPLOY CONCLUIDO!
echo ========================================
echo.
echo Agora execute: setup_credentials.bat
echo para configurar as credenciais do Google Tasks
echo.
pause
