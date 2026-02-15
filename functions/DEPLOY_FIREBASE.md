# 🚀 Deploy Firebase Cloud Functions - Sincronização Automática

## O que você vai ter

✅ Sincronização **100% na nuvem** (não depende do seu computador)  
✅ Sincronização **manual** (quando clicar em "Sync Google")  
✅ Sincronização **automática** (a cada 30 minutos)  
✅ Bidirecional (Hermes ↔ Google Tasks)

---

## Passo 1: Instalar dependências

```bash
cd functions
npm install
```

## Passo 2: Armazenar credenciais no Firestore

```bash
node upload-credentials.js
```

Isso irá:
- Ler o `token.json` (credenciais OAuth)
- Armazenar de forma segura no Firestore
- Permitir que as Cloud Functions acessem o Google Tasks

## Passo 3: Deploy das Cloud Functions

Volte para a raiz do projeto:

```bash
cd ..
firebase deploy --only functions
```

O deploy pode levar 2-5 minutos. Você verá:

```
✔  functions[syncGoogleTasks(us-central1)] Successful create operation.
✔  functions[scheduledSync(us-central1)] Successful create operation.
```

---

## ✅ Pronto!

Agora você tem **2 Cloud Functions** rodando:

### 1. `syncGoogleTasks` (Trigger Manual)
- Dispara quando você clica em "Sync Google" no painel
- Monitora mudanças no documento `system/sync`
- Executa PUSH + PULL

### 2. `scheduledSync` (Automática)
- Roda **a cada 30 minutos** automaticamente
- Mantém tudo sincronizado sem você fazer nada
- Funciona 24/7, mesmo com o computador desligado

---

## 🎯 Como Usar

### Sincronização Manual
1. Abra o painel Hermes
2. Clique em "Sync Google"
3. A Cloud Function executa automaticamente!

### Sincronização Automática
- Não precisa fazer nada!
- A cada 30 minutos sincroniza automaticamente

---

## 📊 Monitorar

### Ver logs em tempo real

```bash
firebase functions:log
```

### Ver logs de uma função específica

```bash
firebase functions:log --only syncGoogleTasks
```

### Painel do Firebase Console

https://console.firebase.google.com/project/gestao-hermes/functions

---

## 💰 Custos

**Firebase Functions - Free Tier:**
- 2 milhões de invocações/mês: GRÁTIS
- 400.000 GB-segundos/mês: GRÁTIS
- 200.000 CPU-segundos/mês: GRÁTIS

**Seu uso estimado:**
- Sincronização manual: ~10-20x/dia = 600x/mês
- Sincronização automática: 48x/dia = 1.440x/mês
- **Total: ~2.000 invocações/mês = 100% GRÁTIS** ✅

---

## 🔧 Ajustar frequência da sincronização automática

Edite `functions/index.js`, linha da função `scheduledSync`:

```javascript
// A cada 30 minutos (padrão)
.schedule('every 30 minutes')

// Outras opções:
.schedule('every 15 minutes')  // Mais frequente
.schedule('every 1 hours')     // Menos frequente
.schedule('every day 00:00')   // Uma vez por dia à meia-noite
```

Depois faça deploy novamente:
```bash
firebase deploy --only functions
```

---

## 🆘 Troubleshooting

### "Permission denied"
```bash
firebase login
firebase use gestao-hermes
```

### "Credentials not found"
Execute novamente:
```bash
cd functions
node upload-credentials.js
```

### Desabilitar sincronização automática
Comente a função no `functions/index.js`:
```javascript
// exports.scheduledSync = functions.pubsub...
```

E faça deploy:
```bash
firebase deploy --only functions
```

---

## 🎉 Benefícios

✅ **Zero manutenção**: Funciona sozinho  
✅ **Sempre disponível**: 24/7 na nuvem  
✅ **Confiável**: Infraestrutura do Google  
✅ **Grátis**: Dentro do free tier  
✅ **Escalável**: Suporta crescimento futuro
