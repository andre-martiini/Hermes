---
type: log
title: Histórico do bundle OKF
description: Registro cronológico de mudanças na documentação operacional do Hermes.
tags: [hermes, okf, changelog]
timestamp: 2026-08-06T00:00:00Z
---

# Log

- **2026-08-06** — Adicionada a integração WhatsApp Cloud API (`functions/whatsapp_cloud.py`, `whatsappCloudWebhook` + `on_whatsapp_cloud_inbound`): processamento de lote de mensagens WhatsApp (texto, áudio, vídeo, imagem) via API oficial da Meta, sem depender de processo local — o usuário encaminha o lote para o número vinculado ao Hermes, fecha com `#resumo` e recebe de volta a transcrição em ordem cronológica e um resumo gerado por Gemini. Novas coleções `whatsapp_cloud_inbound`/`whatsapp_cloud_batches` e índice composto (`sender`+`processed`+`wa_timestamp`) em `firestore.indexes.json`. Documentado o setup (sem exigir CNPJ) em [`whatsapp-cloud-api.md`](/docs/okf/integracoes/whatsapp-cloud-api.md).

- **2026-08-01** — Correções de review (Codex) na PR do planejador de IA: teto diário de `scheduled_notifications` agora é reservado atomicamente numa transação Firestore (`system_usage/ai_planner_notifications/daily/{data}`) em vez de um contador em memória, que não era seguro sob tool calls concorrentes; `consultar_tarefas_ativas` passou a filtrar `status` no próprio Firestore antes do `limit`; `HealthView` só limpa o formulário de exame depois que `onAddExam` resolve com sucesso.
- **2026-08-01** — Adicionado o planejador proativo de notificações por IA (`functions/ai_notification_planner.py`): agente diário sobre Claude que cruza tarefas ativas e metas estratégicas e propõe até 3 notificações/dia via nova coleção `scheduled_notifications`, despachadas pelo `check_and_send_reminders` existente com botões de feedback no Telegram. Documentada também a coleção `estrategia_pessoal`, que já existia mas não estava no schema.
- **2026-06-17** — Migração inicial: documentação operacional solta na raiz do repo (`HABILITAR_BILLING.md`, `QUICKSTART.md`, `SYNC_BADGES_GUIDE.md`, `WHATSAPP_INTEGRATION.md`, `gemini_models_guide.md`, `SOLUCAO_SIMPLIFICADA.md`, `PLAN_MOBILE_BUTTONS.md`, `HANDOFF_OTIMIZACAO_COPILOTO.md`, `functions/DEPLOY.md`, `functions/DEPLOY_FIREBASE.md`) convertida para o formato OKF (frontmatter `type`/`title`/`description`/`tags`/`timestamp` + estrutura hierárquica com `index.md`).
- **2026-06-17** — Removido `copiloto/handoff-otimizacao-2026-06-11.md`: era um handoff pontual de uma tarefa já concluída, não conhecimento de referência. Handoffs desse tipo seguem vivendo em PRs/commits, não no bundle OKF.
- **2026-06-17** — Adicionada categoria `arquitetura/` (schema do Firestore, mapa de Cloud Functions, convenções de frontend) para orientar desenvolvedores e agentes de IA externos. Adicionado `manutencao.md`, definindo gatilhos obrigatórios de atualização desses documentos sempre que a estrutura do sistema mudar.
