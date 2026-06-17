---
type: runbook
title: Deploy das Cloud Functions de sincronização
description: Passo a passo para configurar credenciais e fazer deploy das Cloud Functions de sincronização bidirecional com o Google Tasks (Python e Node.js).
resource: https://console.firebase.google.com/project/gestao-hermes/functions
tags: [hermes, firebase, cloud-functions, google-tasks, deploy]
timestamp: 2026-05-19T17:30:42-03:00
---

# Deploy das Cloud Functions de sincronização

O Hermes oferece duas rotas de deploy equivalentes para sincronização automática com o Google Tasks: a função genérica via `gcloud` (Python, gen2) e o fluxo Firebase CLI (Node.js), que adiciona também a sincronização agendada a cada 30 minutos. Ver pré-requisito de billing em [Habilitar billing no Firebase](/docs/okf/operacoes/habilitar-billing.md).

## O que você vai ter (fluxo Firebase CLI)

- Sincronização 100% na nuvem (não depende do computador local).
- Sincronização manual (botão "Sync Google") e automática (a cada 30 minutos).
- Bidirecional (Hermes ↔ Google Tasks).

## Pré-requisitos (fluxo gcloud)

```bash
gcloud --version
gcloud auth login
gcloud config set project SEU_PROJECT_ID
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable firestore.googleapis.com
```

## Passo 1 — Credenciais do Google Tasks

Fluxo Python (gcloud):
```bash
cd functions
pip install -r requirements.txt
python setup_credentials.py
```
Armazena as credenciais OAuth na coleção Firestore `system/google_credentials`.

Fluxo Node.js (Firebase CLI):
```bash
cd functions
npm install
node upload-credentials.js
```
Lê `token.json` e armazena as credenciais no Firestore.

## Passo 2 — Deploy

Fluxo gcloud (função única `hermes-sync`, trigger por escrita em `system/sync`):
```bash
gcloud functions deploy hermes-sync \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=on_sync_request \
  --trigger-event-filters="type=google.cloud.firestore.document.v1.written" \
  --trigger-event-filters="database=(default)" \
  --trigger-location=us-central1 \
  --trigger-event-filters-path-pattern="document=system/sync"
```

Fluxo Firebase CLI (duas funções: `syncGoogleTasks` manual + `scheduledSync` automática a cada 30 min):
```bash
cd ..
firebase deploy --only functions
```

## Passo 3 — Testar

Clique em "Sync Google" no painel web; a Cloud Function correspondente dispara automaticamente.

## Ajustar frequência da sincronização automática

Edite `functions/index.js`, na função `scheduledSync`:
```javascript
.schedule('every 30 minutes')   // padrão
.schedule('every 15 minutes')
.schedule('every 1 hours')
.schedule('every day 00:00')
```
Depois, `firebase deploy --only functions` novamente.

## Monitoramento

```bash
gcloud functions logs read hermes-sync --region=us-central1 --limit=50
firebase functions:log
firebase functions:log --only syncGoogleTasks
```

Painel: https://console.firebase.google.com/project/gestao-hermes/functions

## Custos

Mesmo free tier descrito em [Habilitar billing no Firebase](/docs/okf/operacoes/habilitar-billing.md): ~2.000 invocações/mês fica 100% dentro do free tier do plano Blaze.

## Troubleshooting

- **Erro de permissões (gcloud):**
  ```bash
  gcloud projects add-iam-policy-binding SEU_PROJECT_ID \
    --member="serviceAccount:SEU_PROJECT_ID@appspot.gserviceaccount.com" \
    --role="roles/datastore.user"
  ```
- **"Permission denied" (Firebase CLI):** `firebase login` e `firebase use gestao-hermes`.
- **"Credentials not found":** repetir `node upload-credentials.js`.
- **Atualizar função:** repetir o comando de deploy correspondente.
- **Deletar função (gcloud):** `gcloud functions delete hermes-sync --region=us-central1`.
- **Desabilitar sincronização automática:** comentar a função `scheduledSync` em `functions/index.js` e fazer deploy novamente.
