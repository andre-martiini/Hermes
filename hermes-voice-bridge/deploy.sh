#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-your-gcp-project-id}"
REGION="${REGION:-southamerica-east1}"
SERVICE_NAME="${SERVICE_NAME:-hermes-voice-bridge}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://your-cloud-run-service-url.run.app}"
FIREBASE_PROJECT_ID="${FIREBASE_PROJECT_ID:-your-firebase-project-id}"
# Origem do app Hermes em producao — o WebSocket /browser-voice-stream recusa
# qualquer outra origem antes mesmo de checar o token.
HERMES_VOICE_ALLOWED_ORIGINS="${HERMES_VOICE_ALLOWED_ORIGINS:-https://your-hermes-app.web.app}"
HERMES_VOICE_MAX_IDLE_SECONDS="${HERMES_VOICE_MAX_IDLE_SECONDS:-90}"

gcloud run deploy "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --source . \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars "PUBLIC_BASE_URL=${PUBLIC_BASE_URL},FIREBASE_PROJECT_ID=${FIREBASE_PROJECT_ID},HERMES_TIMEZONE=America/Sao_Paulo,GOOGLE_APPLICATION_CREDENTIALS=/secrets/firebase-service-account.json,HERMES_VOICE_ALLOWED_ORIGINS=${HERMES_VOICE_ALLOWED_ORIGINS},HERMES_VOICE_MAX_IDLE_SECONDS=${HERMES_VOICE_MAX_IDLE_SECONDS},HERMES_MCP_URL=${HERMES_MCP_URL:-https://us-central1-gestao-hermes.cloudfunctions.net/mcpServer}" \
  --set-secrets "GEMINI_API_KEY=hermes-gemini-api-key:latest,HERMES_VOICE_SECRET_PHRASE=hermes-voice-secret-phrase:latest,TWILIO_ACCOUNT_SID=twilio-account-sid:latest,TWILIO_AUTH_TOKEN=twilio-auth-token:latest,/secrets/firebase-service-account.json=firebase-service-account-json:latest"
