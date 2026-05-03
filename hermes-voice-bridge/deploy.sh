#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-your-gcp-project-id}"
REGION="${REGION:-southamerica-east1}"
SERVICE_NAME="${SERVICE_NAME:-hermes-voice-bridge}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://your-cloud-run-service-url.run.app}"
FIREBASE_PROJECT_ID="${FIREBASE_PROJECT_ID:-your-firebase-project-id}"

gcloud run deploy "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --source . \
  --allow-unauthenticated \
  --port 8080 \
  --set-env-vars "PUBLIC_BASE_URL=${PUBLIC_BASE_URL},FIREBASE_PROJECT_ID=${FIREBASE_PROJECT_ID},HERMES_TIMEZONE=America/Sao_Paulo,GOOGLE_APPLICATION_CREDENTIALS=/secrets/firebase-service-account.json" \
  --set-secrets "GEMINI_API_KEY=hermes-gemini-api-key:latest,HERMES_VOICE_SECRET_PHRASE=hermes-voice-secret-phrase:latest,TWILIO_ACCOUNT_SID=twilio-account-sid:latest,TWILIO_AUTH_TOKEN=twilio-auth-token:latest,/secrets/firebase-service-account.json=firebase-service-account-json:latest"
