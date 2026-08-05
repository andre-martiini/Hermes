# Deploy do hermes-voice-bridge no Cloud Run (us-central1, mesma regiao do mcpServer).
# Rode no PowerShell, dentro de hermes-voice-bridge.

gcloud run deploy hermes-voice-bridge `
  --project gestao-hermes `
  --region us-central1 `
  --source . `
  --allow-unauthenticated `
  --port 8080 `
  --set-env-vars "^;^FIREBASE_PROJECT_ID=gestao-hermes;HERMES_TIMEZONE=America/Sao_Paulo;GOOGLE_APPLICATION_CREDENTIALS=/secrets/firebase-service-account.json;HERMES_VOICE_ALLOWED_ORIGINS=https://gestao-hermes.web.app,https://gestao-hermes.firebaseapp.com;HERMES_VOICE_MAX_IDLE_SECONDS=90;HERMES_VOICE_MAX_SESSION_SECONDS=900;HERMES_MCP_URL=https://us-central1-gestao-hermes.cloudfunctions.net/mcpServer" `
  --set-secrets "GEMINI_API_KEY=hermes-gemini-api-key:latest,HERMES_VOICE_SECRET_PHRASE=hermes-voice-secret-phrase:latest,TWILIO_ACCOUNT_SID=twilio-account-sid:latest,TWILIO_AUTH_TOKEN=twilio-auth-token:latest,/secrets/firebase-service-account.json=firebase-service-account-json:latest"
