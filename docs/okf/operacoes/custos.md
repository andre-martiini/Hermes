---
type: runbook
title: Custos do Hermes — diagnóstico e atribuição
description: Composição real da fatura do projeto gestao-hermes, como atribuir leituras de Firestore e CPU por function, e as consultas BigQuery usadas pelo relatório diário de custos.
resource: https://console.cloud.google.com/billing
tags: [hermes, okf, custos, billing, firestore, bigquery, cloud-functions]
timestamp: 2026-09-08T21:00:00-03:00
---

# Custos do Hermes — diagnóstico e atribuição

Demanda: DEV-2026-0003 · [Issue #203](https://github.com/andre-martiini/Hermes/issues/203).

## 1. Fatura real — 09/08 a 07/09/2026 (projeto `gestao-hermes`)

Total: **R$ 307,57** em 30 dias (orçamento do projeto: R$ 200/mês).

| Item | R$ | % | vs. 30 dias anteriores |
|---|---|---|---|
| Firestore Read Ops — 26,5 M leituras (~885 mil/dia) | 87,50 | 28% | +242% |
| Cloud Run Functions CPU (us-central1) — 782 mil vCPU-s | 84,73 | 28% | +215% |
| Gemini API — 3.5 flash lite R$ 46,5; 3.6 flash R$ 33; embedding R$ 0,20 | 79,87 | 26% | input flash-lite +457% |
| Firestore Entity Writes — 2,48 M | 19,73 | 6% | +25% |
| Cloud Scheduler — 24 jobs | 10,09 | 3% | +96% |
| Cloud Run Services (voice bridge / App Hosting) | 6,55 | 2% | +2732% |
| Artifact Registry — 11 GiB | 6,33 | 2% | +63% |
| Secret Manager — 18 réplicas de versão | 5,59 | 2% | +196% |
| Functions Memory, egress Firestore, Storage, Cloud Build | ~5,5 | 2% | — |

Leitura: infraestrutura de leitura + CPU = 62%; IA = 26%. **Deploy (Cloud Build + Artifact Registry) não é o problema** (R$ 6,43).

Custos **fora do GCP** gerados pelo Hermes, sem alerta e (até o PR 2) sem telemetria: Anthropic (Godmode, planejador de notificações, secretário WhatsApp, elevações — `claude-fable-5`), OpenAI (`gpt-5.6-luna`), Groq (Whisper), Tavily, Twilio.

## 2. Por que a fatura não diz "quem"

O Billing agrega Firestore por SKU (leitura/escrita), sem coleção nem chamador. A CPU das functions vem por região, não por serviço, no export padrão. Por isso a atribuição é feita em duas camadas:

### 2.1 `firestore_metrics.py` (backend Python)

Intercepta `DocumentReference.get/set/update/delete/create`, `Query.stream`, `Client.get_all`, `WriteBatch.commit` e `Transaction._commit`, e acumula por function (`K_SERVICE`) e por coleção raiz. Grava com `Increment` em:

```
system_usage/firestore/daily/{YYYY-MM-DD}
  total:       {reads, writes, queries}
  services:    {<function>: {reads, writes, queries}}
  collections: {<colecao>: {reads, writes}}
```

Custo da telemetria: ≤ 1 escrita/min por instância ativa. Não cobre o frontend (110 listeners `onSnapshot`) nem as functions Node — **frontend + Node ≈ leituras faturadas − `total.reads` medido**.

Desligar: `HERMES_FIRESTORE_METRICS=0`. Ajustes: `HERMES_FIRESTORE_METRICS_FLUSH_S` (padrão 60), `HERMES_FIRESTORE_METRICS_FLUSH_OPS` (padrão 2000).

### 2.2 Export do Billing para BigQuery (ativado em 08/09/2026)

Sem retroativo: só há dados a partir da ativação. Duas tabelas possíveis no dataset escolhido:

- `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>` — **custo padrão**: serviço, SKU, projeto, dia.
- `gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>` — **custo detalhado de uso**: acrescenta `resource.name` (= serviço Cloud Run = function). É o que permite CPU por function. Se ainda não estiver ligado, ligar em Faturamento → Exportação de faturamento → "Custo detalhado de uso".

Consulta do dia anterior por serviço/SKU (usada pelo relatório diário — PR 1):

```sql
DECLARE dia DATE DEFAULT DATE_SUB(CURRENT_DATE('America/Sao_Paulo'), INTERVAL 1 DAY);
SELECT service.description AS servico, sku.description AS sku,
       ROUND(SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)), 4) AS custo_brl,
       SUM(usage.amount) AS uso, ANY_VALUE(usage.unit) AS unidade
FROM `gestao-hermes.<DATASET>.gcp_billing_export_v1_<BILLING_ACCOUNT_ID>`
WHERE project.id = 'gestao-hermes'
  AND DATE(usage_start_time, 'America/Sao_Paulo') = dia
GROUP BY servico, sku
ORDER BY custo_brl DESC;
```

CPU por function (exige o export detalhado):

```sql
SELECT resource.name AS function_name,
       ROUND(SUM(cost), 4) AS custo_brl, SUM(usage.amount) AS vcpu_segundos
FROM `gestao-hermes.<DATASET>.gcp_billing_export_resource_v1_<BILLING_ACCOUNT_ID>`
WHERE project.id = 'gestao-hermes'
  AND service.description = 'Cloud Run Functions'
  AND sku.description LIKE '%CPU%'
  AND DATE(usage_start_time, 'America/Sao_Paulo') >= DATE_SUB(CURRENT_DATE('America/Sao_Paulo'), INTERVAL 7 DAY)
GROUP BY function_name ORDER BY custo_brl DESC LIMIT 20;
```

Permissão necessária para a function do relatório: `roles/bigquery.jobUser` no projeto e `roles/bigquery.dataViewer` no dataset, para a service account das Cloud Functions (`gestao-hermes@appspot.gserviceaccount.com` ou a SA de compute padrão, conforme o deploy).

## 3. Candidatos a maior consumo (a confirmar com os dados acima)

- `scheduled_sync` (30 min, 1 GB, 540 s): lê `tarefas` inteira + 11 outros `.stream()` sem filtro; reescreve tarefas → cada escrita dispara 6 triggers; `log_to_firestore` grava linha a linha em `system/sync`.
- `check_and_send_reminders` (1 min, 1 GB → 0,583 vCPU): 43.200 execuções/mês.
- Frontend: 110 listeners `onSnapshot` sobre coleções inteiras; cada aba aberta relê tudo.
- `monitorar_acervo_global` (15 min), `detectar_atencao_acoes` (30 min), `vencer_promessas` (15 min), `scheduled_page_monitor` (30 min), `scheduledSipacSync` Node (2 h).

## 4. Roteiro da demanda

| PR | Entrega | Estado |
|---|---|---|
| 0 | `firestore_metrics.py` + este runbook | este PR |
| 1 | `relatorio_diario_custos` às 19h BRT (BigQuery + Gemini + Claude + Firestore por function), substitui `relatorio_diario_custo_gemini` | pendente do nome do dataset |
| 2 | Telemetria Claude/OpenAI/Groq/Tavily + rotear ~50 chamadas Gemini diretas por `generate_content_logged` | — |
| 3 | Cortes guiados pelos dados (sync só grava diff; reminders 256 MB; listeners por view; cadências; Secret Manager 1 região; limpeza do Artifact Registry) | após 3–5 dias de medição |

Meta: fatura GCP do Hermes ≤ R$ 150/mês sem remover funcionalidade.
