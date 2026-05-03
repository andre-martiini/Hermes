@echo off
setlocal

if "%PROJECT_ID%"=="" set "PROJECT_ID=your-gcp-project-id"
if "%REGION%"=="" set "REGION=southamerica-east1"
if "%SERVICE_NAME%"=="" set "SERVICE_NAME=hermes-voice-bridge"
if "%PUBLIC_BASE_URL%"=="" set "PUBLIC_BASE_URL=https://your-cloud-run-service-url.run.app"
if "%FIREBASE_PROJECT_ID%"=="" set "FIREBASE_PROJECT_ID=your-firebase-project-id"

gcloud run deploy "%SERVICE_NAME%" ^
  --project "%PROJECT_ID%" ^
  --region "%REGION%" ^
  --source . ^
  --allow-unauthenticated ^
  --port 8080 ^
  --set-env-vars "PUBLIC_BASE_URL=%PUBLIC_BASE_URL%,FIREBASE_PROJECT_ID=%FIREBASE_PROJECT_ID%,HERMES_TIMEZONE=America/Sao_Paulo,GOOGLE_APPLICATION_CREDENTIALS=/secrets/firebase-service-account.json" ^
  --set-secrets "GEMINI_API_KEY=hermes-gemini-api-key:latest,HERMES_VOICE_SECRET_PHRASE=hermes-voice-secret-phrase:latest,TWILIO_ACCOUNT_SID=twilio-account-sid:latest,TWILIO_AUTH_TOKEN=twilio-auth-token:latest,/secrets/firebase-service-account.json=firebase-service-account-json:latest"

endlocal
