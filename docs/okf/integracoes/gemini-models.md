---
type: reference
title: Modelos Gemini disponíveis e preferências
description: Modelos Gemini 2.0/2.5 usados pelo Hermes, preferências de uso e tratamento de erros conhecidos.
tags: [hermes, gemini, llm, configuracao]
timestamp: 2026-05-19T17:30:42-03:00
---

# Modelos Gemini disponíveis e preferências (2025)

## Visão geral

Desde o início/meados de 2025, o Google migrou para as séries Gemini 2.0 e 2.5. A série 1.5 é legada e não deve ser usada no Hermes.

## Modelos disponíveis (verificado fev–ago 2025)

- `gemini-2.5-flash-lite`: otimizado para velocidade e custo. Modelo priorizado por André Martini para o bot Hermes.
- `gemini-2.5-pro`: alta inteligência, janela de contexto ampla, thinking.
- `gemini-2.5-flash`: balanceado para uso geral.
- `gemini-2.0-flash`: versão estável padrão da série 2.0.
- `gemini-2.0-pro`: flagship para raciocínio complexo e contexto grande.
- `gemini-2.0-flash-lite`: predecessor do 2.5 lite.

## Conhecimento operacional

- **Compatibilidade:** modelos Flash-Lite (2.0 e 2.5) podem ter limitações ao combinar Function Calling customizado com a tool nativa de Google Search em certas versões de SDK, gerando `400 INVALID_ARGUMENT`.
- **Preferência:** sempre usar a série 2.5 quando possível; evitar referenciar modelos 1.5.
- **Tratamento de erros:**
  - `503 UNAVAILABLE`: alta demanda no modelo lite específico. Pausar e tentar novamente, ou trocar temporariamente pelo Pro correspondente se urgente.
  - `403 PERMISSION_DENIED` (vazamento de API key): garantir que as chaves fiquem em arquivos `.env`, nunca hardcoded em `.py`/`.tsx` que possam ir para produção ou repositório público.

## Armazenamento de chaves

- Arquivos `.env` locais usados em `Hermes-Bot/` e na raiz do projeto.
- `.gitignore` deve incluir explicitamente `.env` e `.env.local` para prevenir vazamentos.
