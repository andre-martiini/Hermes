# Deploy automático no Firebase (CI/CD)

Este repositório publica o sistema **Hermes** no Firebase (projeto
`gestao-hermes`) automaticamente sempre que algo entra na branch **`main`**
— ou seja, **a cada merge**. A automação está em
[`.github/workflows/deploy.yml`](./deploy.yml).

O que é publicado em cada deploy:

- **Hosting** — frontend React/Vite (pasta `dist`)
- **Functions Python** (`functions/`)
- **Functions Node** (`functions_node/`)
- **Firestore indexes** (`firestore.indexes.json`)
- **Storage rules** (`storage.rules`)

Antes de publicar, o workflow roda `npm test`. **Se algum teste falhar, o
deploy não acontece.**

---

## Configuração única (você precisa fazer isto uma vez)

O workflow depende de **2 secrets** no GitHub. Sem eles, o deploy falha.

Vá em: **repositório no GitHub → Settings → Secrets and variables → Actions
→ New repository secret** e crie os dois abaixo.

### 1. `FIREBASE_SERVICE_ACCOUNT`

Credencial (JSON) de uma *Service Account* do Google Cloud com permissão para
fazer deploy no projeto `gestao-hermes`.

Como gerar:

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/iam-admin/serviceaccounts?project=gestao-hermes)
   (projeto `gestao-hermes`).
2. **Create Service Account** (ex.: nome `github-deploy`).
3. Conceda os papéis (roles) necessários para o deploy completo:
   - `Firebase Admin` (ou, de forma mais granular, `Firebase Hosting Admin`)
   - `Cloud Functions Admin`
   - `Cloud Run Admin` (Functions de 2ª geração rodam sobre Cloud Run)
   - `Cloud Build Editor`
   - `Artifact Registry Administrator`
   - `Service Account User`
   - `Cloud Datastore Index Admin` (para os índices do Firestore)
   - `Firebase Rules Admin` (para as regras do Storage)
   - `Cloud Scheduler Admin` (para as functions **agendadas**, que criam/atualizam
     jobs do Cloud Scheduler — ex.: `scheduled_sync`, `check_and_send_reminders`)
   - `Secret Manager Admin` *(somente se o deploy precisar criar/atualizar
     secrets das functions)*
4. Na aba **Keys** da Service Account → **Add Key → Create new key → JSON**.
5. Abra o arquivo `.json` baixado, **copie todo o conteúdo** e cole no valor
   do secret `FIREBASE_SERVICE_ACCOUNT`.

> Dica: se preferir o mínimo de configuração e já confiar na conta, o papel
> `Editor` + `Firebase Admin` no projeto também funciona — mas a lista acima é
> a recomendação de menor privilégio.

> **APIs do projeto:** o deploy de Cloud Functions de 2ª geração também exige que
> a **Cloud Billing API** esteja habilitada no projeto. Habilite em:
> https://console.cloud.google.com/apis/library/cloudbilling.googleapis.com?project=gestao-hermes

### 2. `GEMINI_API_KEY`

A chave da API Gemini usada no **build do frontend** (o Vite a embute no
bundle em tempo de build — veja `vite.config.ts`). Use a mesma chave que você
usa hoje no seu `.env` local. Cole o valor cru (sem aspas) no secret.

---

## Como usar no dia a dia

- **Automático:** faça o merge de um PR (ou um push direto) na branch `main`.
  O deploy dispara sozinho.
- **Manual:** aba **Actions → Deploy Hermes (Firebase) → Run workflow**.

Acompanhe o progresso e os logs na aba **Actions** do GitHub.

---

## Observações importantes

- **Secrets/variáveis das Cloud Functions:** este workflow apenas *publica* o
  código. As variáveis de ambiente e secrets que as functions consomem em
  runtime precisam já estar configuradas no projeto (Secret Manager /
  `firebase functions:secrets`). O deploy não as cria a partir do seu `.env`
  local.
- **Passos manuais que NÃO estão automatizados** (eram feitos pelos scripts
  `.bat` e geralmente são de configuração única): criação do tópico Pub/Sub
  `hermes-telegram-tool-dispatch`, registro do webhook do Telegram e o
  `upload-credentials.js`. Rode-os manualmente quando necessário.
- **Primeiro deploy pode pedir APIs habilitadas** (Cloud Functions, Cloud
  Build, Artifact Registry, Cloud Run). Se o primeiro run falhar por isso,
  habilite as APIs no projeto e rode novamente.
