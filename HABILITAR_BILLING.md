# ⚠️ Ação Necessária: Habilitar Billing no Firebase

## O que aconteceu?

O deploy das Cloud Functions falhou porque o projeto Firebase está no **plano Spark (gratuito)**, que não suporta Cloud Functions.

## ✅ Solução: Upgrade para Plano Blaze

O plano **Blaze** é pay-as-you-go, mas tem um **free tier muito generoso**:

### Free Tier do Plano Blaze:
- ✅ 2 milhões de invocações/mês: **GRÁTIS**
- ✅ 400.000 GB-segundos/mês: **GRÁTIS**
- ✅ 200.000 CPU-segundos/mês: **GRÁTIS**
- ✅ 5 GB de tráfego de rede/mês: **GRÁTIS**

### Seu uso estimado:
- Sincronização manual: ~20x/dia = 600x/mês
- Sincronização automática (30 min): 48x/dia = 1.440x/mês
- **Total: ~2.000 invocações/mês**

**Resultado: 100% dentro do free tier = R$ 0,00/mês** 🎉

---

## 📋 Como Habilitar (Passo a Passo)

### 1. Acesse o Firebase Console

https://console.firebase.google.com/project/gestao-hermes/overview

### 2. Clique em "Upgrade"

No menu lateral esquerdo, você verá um botão "Upgrade" ou "Fazer upgrade"

### 3. Selecione o Plano Blaze

- Escolha "Blaze (Pay as you go)"
- **NÃO se preocupe**: Você só paga se ultrapassar o free tier

### 4. Configure o Billing

- Vincule um cartão de crédito (necessário, mas não será cobrado se ficar no free tier)
- **Dica**: Configure um orçamento de alerta (ex: R$ 10) para ser notificado se ultrapassar

### 5. Confirme o Upgrade

Após confirmar, aguarde 1-2 minutos para as mudanças serem aplicadas

---

## 🔒 Proteção Contra Custos Inesperados

### Configure um Orçamento de Alerta:

1. Acesse: https://console.cloud.google.com/billing
2. Clique em "Orçamentos e alertas"
3. Crie um novo orçamento:
   - Nome: "Alerta Hermes"
   - Valor: R$ 10,00 (ou USD $2)
   - Alerta em: 50%, 90%, 100%

Você receberá email se começar a ter custos!

---

## 🚀 Depois do Upgrade

Execute novamente o deploy:

```bash
.\deploy_cloud.bat
```

Ou manualmente:

```bash
firebase deploy --only functions
```

---

## ❓ FAQ

### "Vou ser cobrado?"

**NÃO**, se ficar dentro do free tier (que é o seu caso). O free tier é renovado mensalmente.

### "E se eu ultrapassar o free tier?"

Você receberá alertas por email. Além disso, o custo é muito baixo:
- Cada 1 milhão de invocações extras: ~USD $0.40

### "Posso voltar para o plano Spark?"

Sim, mas perderá acesso às Cloud Functions. Você pode fazer downgrade a qualquer momento.

### "Existe alternativa sem billing?"

Sim, continuar usando o script local (`start.bat`), mas você precisará deixar o computador ligado.

---

## 📊 Monitorar Uso

Após habilitar, você pode monitorar o uso em:

https://console.firebase.google.com/project/gestao-hermes/usage

---

**Após habilitar o billing, execute novamente o deploy e tudo funcionará!** 🚀
