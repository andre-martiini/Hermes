---
type: runbook
title: Habilitar billing no Firebase
description: Passo a passo para fazer upgrade do projeto Firebase do plano Spark para o Blaze, necessário para deploy de Cloud Functions.
resource: https://console.firebase.google.com/project/gestao-hermes/overview
tags: [hermes, firebase, billing, cloud-functions]
timestamp: 2026-05-19T17:30:42-03:00
---

# Habilitar billing no Firebase

## O que aconteceu?

O deploy das Cloud Functions falhou porque o projeto Firebase está no plano Spark (gratuito), que não suporta Cloud Functions.

## Solução: upgrade para plano Blaze

O plano Blaze é pay-as-you-go, mas tem um free tier muito generoso:

- 2 milhões de invocações/mês: grátis
- 400.000 GB-segundos/mês: grátis
- 200.000 CPU-segundos/mês: grátis
- 5 GB de tráfego de rede/mês: grátis

Uso estimado do Hermes: sincronização manual (~600x/mês) + automática a cada 30 min (~1.440x/mês) = ~2.000 invocações/mês, 100% dentro do free tier.

## Como habilitar

1. Acesse https://console.firebase.google.com/project/gestao-hermes/overview
2. Clique em "Upgrade" no menu lateral.
3. Selecione "Blaze (Pay as you go)". Você só paga se ultrapassar o free tier.
4. Vincule um cartão de crédito e configure um orçamento de alerta (ex: R$ 10).
5. Confirme o upgrade e aguarde 1-2 minutos.

## Proteção contra custos inesperados

Em https://console.cloud.google.com/billing, crie um orçamento ("Orçamentos e alertas"):
- Nome: "Alerta Hermes"
- Valor: R$ 10,00 (ou USD $2)
- Alertas em: 50%, 90%, 100%

## Depois do upgrade

```bash
.\deploy_cloud.bat
```

ou manualmente:

```bash
firebase deploy --only functions
```

## FAQ

- **Vou ser cobrado?** Não, se ficar dentro do free tier. O free tier é renovado mensalmente.
- **E se ultrapassar?** Você recebe alertas por email; o custo extra é baixo (~USD $0.40 por milhão de invocações extras).
- **Posso voltar ao plano Spark?** Sim, mas perde acesso às Cloud Functions.
- **Existe alternativa sem billing?** Sim — ver [sincronização local](/docs/okf/operacoes/sincronizacao-local.md).

## Monitorar uso

https://console.firebase.google.com/project/gestao-hermes/usage
