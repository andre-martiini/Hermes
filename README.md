# Hermes - Sistema de Gestão de Tarefas

Sistema integrado de gestão de tarefas com sincronização automática com Google Tasks.

## 🚀 Funcionalidades

- ✅ Gestão completa de tarefas e projetos
- ✅ Sincronização bidirecional com Google Tasks
- ✅ Categorização automática (CLC, Assistência Estudantil, etc.)
- ✅ Plano de Trabalho Mensal
- ✅ Auditoria PGC
- ✅ Ferramentas de Brainstorming com IA

## 📦 Instalação

### 1. Instalar dependências do frontend

```bash
npm install
```

### 2. Configurar Firebase

1. Crie um projeto no [Firebase Console](https://console.firebase.google.com/)
2. Baixe o arquivo `firebase_service_account_key.json` e coloque na raiz do projeto
3. Configure o Firestore Database

### 3. Configurar Google Tasks API

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/)
2. Habilite a Google Tasks API
3. Crie credenciais OAuth 2.0
4. Baixe o arquivo `credentials.json` e coloque na raiz do projeto

## 🔧 Desenvolvimento Local

### Iniciar o frontend

```bash
npm run dev
```

### Opção 1: Rodar sincronização localmente (temporário)

```bash
python hermes_cli.py watch
```

### Opção 2: Deploy da Cloud Function (recomendado)

#### Passo 1: Configurar credenciais

```bash
setup_credentials.bat
```

Isso irá:
- Autenticar com sua conta Google
- Armazenar credenciais de forma segura no Firestore

#### Passo 2: Fazer deploy da Cloud Function

```bash
deploy_function.bat
```

Após o deploy, a sincronização acontecerá **automaticamente** sempre que você clicar em "Sync Google" no painel!

## 🌐 Cloud Function

A Cloud Function monitora o documento `system/sync` no Firestore e executa automaticamente:

1. **PUSH**: Envia tarefas do Firestore para o Google Tasks
2. **PULL**: Importa tarefas do Google Tasks para o Firestore

### Vantagens

- ✅ Serverless (sem necessidade de servidor rodando)
- ✅ Automático (dispara ao clicar no botão)
- ✅ Escalável
- ✅ Econômico (provavelmente grátis no free tier)

### Monitorar logs

```bash
gcloud functions logs read hermes-sync --region=us-central1 --limit=50
```

## 📁 Estrutura do Projeto

```
Hermes/
├── functions/              # Cloud Function para sincronização
│   ├── main.py            # Código principal da função
│   ├── setup_credentials.py  # Script de configuração
│   ├── requirements.txt   # Dependências Python
│   └── DEPLOY.md          # Guia de deploy detalhado
├── public/                # Arquivos estáticos
├── index.tsx              # Aplicação React principal
├── firebase.ts            # Configuração Firebase
├── hermes_cli.py          # CLI local (opcional)
├── deploy_function.bat    # Script de deploy
└── setup_credentials.bat  # Script de setup
```

## 🔐 Segurança

- As credenciais do Google Tasks são armazenadas de forma segura no Firestore
- Nunca commite arquivos sensíveis (`.json` com credenciais)
- Use variáveis de ambiente para dados sensíveis em produção

## 📝 Classificação de Tarefas

Use tags no título ou notas das tarefas:

- `[CLC]` ou `Tag: CLC` → Categoria CLC
- `[ASSISTÊNCIA]` ou `Tag: ASSISTÊNCIA` → Assistência Estudantil
- `[GERAL]` ou `Tag: GERAL` → Geral
- Sem tag → Não Classificada

## 🆘 Troubleshooting

### Sincronização não funciona

1. Verifique se a Cloud Function foi deployada: `gcloud functions list`
2. Veja os logs: `gcloud functions logs read hermes-sync --region=us-central1`
3. Confirme que as credenciais foram configuradas: verifique `system/google_credentials` no Firestore

### Erro de permissões

```bash
gcloud projects add-iam-policy-binding SEU_PROJECT_ID \
  --member="serviceAccount:SEU_PROJECT_ID@appspot.gserviceaccount.com" \
  --role="roles/datastore.user"
```

## 📄 Licença

MIT
