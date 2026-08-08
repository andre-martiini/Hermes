---
type: index
title: Documentação Operacional do Hermes
description: Índice raiz do bundle OKF (Open Knowledge Format) com arquitetura, runbooks, guias de integração e documentação operacional do Hermes.
tags: [hermes, okf, indice]
timestamp: 2026-06-17T00:00:00Z
---

# Documentação Operacional do Hermes (OKF)

Este diretório é um bundle [Open Knowledge Format](https://github.com/ — ver anúncio do formato) com a documentação operacional e de arquitetura do Hermes, destinada tanto a desenvolvedores quanto a agentes de IA que venham desenvolver o sistema. O knowledge graph de produção (nós conceituais, embeddings, RAG) continua em Firestore — ver `functions/knowledge_graph.py` — e não é afetado por este bundle.

**Antes de editar qualquer documento aqui, leia [manutencao.md](/docs/okf/manutencao.md)** — define quando um documento precisa ser atualizado e o que não deve entrar neste bundle.

## Categorias

- [Arquitetura](/docs/okf/arquitetura/index.md) — schema do Firestore, mapa de Cloud Functions e convenções de frontend.
- [Operações](/docs/okf/operacoes/index.md) — deploy, billing, sincronização e badges.
- [Integrações](/docs/okf/integracoes/index.md) — WhatsApp e modelos Gemini.
- [Guias](/docs/okf/guias/index.md) — primeiros passos para rodar o sistema.
- [UI](/docs/okf/ui/index.md) — decisões de interface.
- [Copiloto](/docs/okf/copiloto/index.md) — documentação viva sobre arquitetura e funcionamento do Copiloto Hermes.
- [Propostas](/docs/okf/propostas/vinculo-email-acao.md) — propostas de funcionalidade ainda não implementadas (removidas do bundle após execução, conforme `manutencao.md`).

Ver [log.md](/docs/okf/log.md) para o histórico de mudanças deste bundle.
