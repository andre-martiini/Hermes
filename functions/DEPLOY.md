# Guia de Deploy da Cloud Function para Sincronização Google Tasks

## Pré-requisitos

1. **Google Cloud CLI instalado**
   ```bash
   # Instale o gcloud CLI: https://cloud.google.com/sdk/docs/install
   gcloud --version
   ```

2. **Projeto Firebase configurado**
   ```bash
   # Faça login
   gcloud auth login
   
   # Configure o projeto (substitua pelo ID do seu projeto)
   gcloud config set project SEU_PROJECT_ID
   ```

3. **Habilite as APIs necessárias**
   ```bash
   gcloud services enable cloudfunctions.googleapis.com
   gcloud services enable cloudbuild.googleapis.com
   gcloud services enable firestore.googleapis.com
   ```

## Passo 1: Configurar Credenciais do Google Tasks

Antes de fazer o deploy, você precisa armazenar as credenciais do Google Tasks no Firestore:

```bash
cd functions
pip install -r requirements.txt
python setup_credentials.py
```

Isso irá:
- Autenticar com sua conta Google
- Armazenar as credenciais de forma segura no Firestore (coleção `system/google_credentials`)

## Passo 2: Deploy da Cloud Function

Execute o comando de deploy:

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

### Explicação dos parâmetros:

- `--gen2`: Usa a 2ª geração de Cloud Functions (mais moderna)
- `--runtime=python311`: Usa Python 3.11
- `--region=us-central1`: Região onde a função será hospedada
- `--entry-point=on_sync_request`: Nome da função no código
- `--trigger-event-filters`: Configura o trigger para monitorar o documento `system/sync`

## Passo 3: Testar a Function

Após o deploy, teste clicando em "Sync Google" no painel web. A Cloud Function será disparada automaticamente!

## Monitoramento

Para ver os logs da função:

```bash
gcloud functions logs read hermes-sync --region=us-central1 --limit=50
```

## Custos

- **Cloud Functions**: Grátis até 2 milhões de invocações/mês
- **Firestore**: Grátis até 50k leituras e 20k escritas por dia
- Para este uso, provavelmente ficará no free tier!

## Troubleshooting

### Erro de permissões
```bash
# Garanta que a service account tem permissões adequadas
gcloud projects add-iam-policy-binding SEU_PROJECT_ID \
  --member="serviceAccount:SEU_PROJECT_ID@appspot.gserviceaccount.com" \
  --role="roles/datastore.user"
```

### Atualizar a função
Para atualizar após mudanças no código, basta executar o comando de deploy novamente.

### Deletar a função
```bash
gcloud functions delete hermes-sync --region=us-central1
```

## Vantagens desta solução

✅ **Serverless**: Não precisa manter servidor rodando  
✅ **Automático**: Dispara automaticamente quando você clica em "Sync Google"  
✅ **Escalável**: Suporta múltiplas requisições simultâneas  
✅ **Econômico**: Provavelmente grátis no free tier  
✅ **Confiável**: Infraestrutura gerenciada pelo Google  
