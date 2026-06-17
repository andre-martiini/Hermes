---
type: log
title: Histórico do bundle OKF
description: Registro cronológico de mudanças na documentação operacional do Hermes.
tags: [hermes, okf, changelog]
timestamp: 2026-06-17T00:00:00Z
---

# Log

- **2026-06-17** — Migração inicial: documentação operacional solta na raiz do repo (`HABILITAR_BILLING.md`, `QUICKSTART.md`, `SYNC_BADGES_GUIDE.md`, `WHATSAPP_INTEGRATION.md`, `gemini_models_guide.md`, `SOLUCAO_SIMPLIFICADA.md`, `PLAN_MOBILE_BUTTONS.md`, `HANDOFF_OTIMIZACAO_COPILOTO.md`, `functions/DEPLOY.md`, `functions/DEPLOY_FIREBASE.md`) convertida para o formato OKF (frontmatter `type`/`title`/`description`/`tags`/`timestamp` + estrutura hierárquica com `index.md`).
- **2026-06-17** — Removido `copiloto/handoff-otimizacao-2026-06-11.md`: era um handoff pontual de uma tarefa já concluída, não conhecimento de referência. Handoffs desse tipo seguem vivendo em PRs/commits, não no bundle OKF.
