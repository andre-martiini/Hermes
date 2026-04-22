@echo off
setlocal EnableDelayedExpansion

echo =========================================
echo   HERMES - DEPLOY COMPLETO (v2 Low-Latency)
echo =========================================
echo.

REM -------------------------------------------------------
REM Validacoes iniciais
REM -------------------------------------------------------
where firebase >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Firebase CLI nao encontrado.
    echo        Instale com: npm install -g firebase-tools
    pause & exit /b 1
)

where gcloud >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [AVISO] gcloud CLI nao encontrado. Pulando etapa de Pub/Sub.
    set SKIP_GCLOUD=1
) else (
    set SKIP_GCLOUD=0
)

REM -------------------------------------------------------
REM [1/4] Firestore indexes (TTL para idempotency e sessions)
REM -------------------------------------------------------
echo [1/4] Publicando indexes e TTL do Firestore...
firebase deploy --only firestore:indexes --project gestao-hermes

if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Falha ao publicar indexes do Firestore.
    pause & exit /b 1
)
echo       OK - TTL ativo em idempotency.expires_at e telegram_sessions.expires_at
echo.

REM -------------------------------------------------------
REM [2/4] Whitelist inicial no Firestore (se TELEGRAM_CHAT_ID definido)
REM -------------------------------------------------------
echo [2/4] Verificando whitelist do Telegram...
if defined TELEGRAM_CHAT_ID (
    echo       Criando entrada na whitelist para chat_id=%TELEGRAM_CHAT_ID%
    call gcloud firestore documents create ^
        "projects/gestao-hermes/databases/(default)/documents/whitelist/%TELEGRAM_CHAT_ID%" ^
        --fields="active=true,name=Owner,added_at=$(date -u +%%Y-%%m-%%dT%%H:%%M:%%SZ)" ^
        --project=gestao-hermes 2>nul || echo       [INFO] Documento ja existe ou gcloud nao disponivel.
) else (
    echo       TELEGRAM_CHAT_ID nao definido. Whitelist usara ALLOWED_TELEGRAM_CHAT_ID da env var.
    echo       Para adicionar via Firestore: crie doc em whitelist/{chat_id} com campo active=true
)
echo.

REM -------------------------------------------------------
REM [3/4] Deploy das Cloud Functions Python
REM -------------------------------------------------------
echo [3/4] Garantindo topico Pub/Sub e fazendo deploy das Cloud Functions...
if "%SKIP_GCLOUD%"=="0" (
    echo       Garantindo topico hermes-telegram-tool-dispatch...
    call gcloud pubsub topics create hermes-telegram-tool-dispatch --project=gestao-hermes 2>nul || echo       [INFO] Topico ja existe.
)
echo.
firebase deploy --only functions:python --project gestao-hermes

if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Falha no deploy das functions.
    pause & exit /b 1
)
echo.
echo       OK - telegramWebhook, on_telegram_inbound e on_telegram_tool_dispatch atualizados
echo.

REM -------------------------------------------------------
REM [4/4] Registrar webhook do Telegram
REM -------------------------------------------------------
echo [4/4] Atualizando webhook do Telegram...
echo.
echo       Para registrar o webhook, execute o comando abaixo
echo       (substitua TOKEN e URL pela URL real da function):
echo.
echo   curl -X POST "https://api.telegram.org/bot^<TOKEN^>/setWebhook" ^
echo        -d "url=https://southamerica-east1-gestao-hermes.cloudfunctions.net/telegramWebhook"
echo.
echo       Ou acesse setup_bot.bat se estiver configurado.
echo.

REM -------------------------------------------------------
REM Resumo final
REM -------------------------------------------------------
echo =========================================
echo   DEPLOY CONCLUIDO
echo =========================================
echo.
echo   Mudancas da v2 (Low-Latency):
echo   - Roteamento 2 estagios via Flash Lite
echo   - Slot-filling estruturado (sem historico bruto)
echo   - Idempotencia por update_id (TTL 24h)
echo   - Auth via whitelist Firestore (cache 5min)
echo   - trace_id propagado em todos os logs
echo   - Worker Pub/Sub para execucao final de tools
echo   - editMessageText para feedback assincrono
echo   - Catalogo backend expandido para 27 tools roteaveis
echo.
echo   Colecoes Firestore novas:
echo   - whitelist/{chat_id}   - usuarios autorizados
echo   - idempotency/{update_id} - dedup (TTL 24h)
echo   - telegram_sessions/{chat_id} - sessoes (TTL 30min)
echo.
echo   Para monitorar: firebase functions:log --project gestao-hermes
echo.
pause
