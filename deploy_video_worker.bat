@echo off
REM Deploy do hermes-video-worker (Cloud Run Job do Hermes Video).
REM Rodar na raiz do repositorio, com o gcloud autenticado numa conta com acesso ao gestao-hermes.

echo ========================================
echo   HERMES VIDEO - DEPLOY DO WORKER
echo ========================================
echo.

where gcloud >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Google Cloud CLI nao encontrado!
    echo Instale: https://cloud.google.com/sdk/docs/install
    pause
    exit /b 1
)

set PROJETO=gestao-hermes
set REGIAO=us-central1
set IMAGEM=us-central1-docker.pkg.dev/%PROJETO%/hermes/hermes-video-worker:latest
set CONTA=1003307358410-compute@developer.gserviceaccount.com

echo [1/4] Projeto e APIs...
gcloud config set project %PROJETO%
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com

echo.
echo [2/4] Repositorio de imagens (ignora "ja existe")...
gcloud artifacts repositories create hermes --repository-format=docker --location=%REGIAO% 2>nul

echo.
echo [3/4] Build da imagem (Cloud Build, a partir da raiz)...
gcloud builds submit --config services/video-worker/cloudbuild.yaml --substitutions=_IMAGEM=%IMAGEM% .
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Build falhou.
    pause
    exit /b 1
)

echo.
echo [4/4] Job do Cloud Run (1 h, 2 GB, sem retentativa automatica)...
gcloud run jobs deploy hermes-video-worker --image=%IMAGEM% --region=%REGIAO% --service-account=%CONTA% --task-timeout=3600 --max-retries=0 --memory=2Gi --cpu=2 --tasks=1

echo.
echo ========================================
echo   DEPLOY CONCLUIDO
echo   Rodar um projeto:
echo   gcloud run jobs execute hermes-video-worker --region=%REGIAO% --update-env-vars VIDEO_PROJETO_ID=^<id^>
echo ========================================
