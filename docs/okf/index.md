---
type: index
title: Documentação Operacional do Hermes
description: Índice raiz do bundle OKF (Open Knowledge Format) com runbooks, guias de integração e handoffs operacionais do Hermes.
tags: [hermes, okf, indice]
timestamp: 2026-06-17T00:00:00Z
---

# Documentação Operacional do Hermes (OKF)

Este diretório é um bundle [Open Knowledge Format](https://github.com/ — ver anúncio do formato) com a documentação operacional do Hermes que antes vivia como arquivos `.md` soltos na raiz do repositório. O knowledge graph de produção (nós conceituais, embeddings, RAG) continua em Firestore — ver `functions/knowledge_graph.py` — e não é afetado por este bundle.

## Categorias

- [Operações](/docs/okf/operacoes/index.md) — deploy, billing, sincronização e badges.
- [Integrações](/docs/okf/integracoes/index.md) — WhatsApp e modelos Gemini.
- [Guias](/docs/okf/guias/index.md) — primeiros passos para rodar o sistema.
- [UI](/docs/okf/ui/index.md) — decisões de interface.
- [Copiloto](/docs/okf/copiloto/index.md) — handoffs de otimização do Copiloto Hermes.

Ver [log.md](/docs/okf/log.md) para o histórico de mudanças deste bundle.
