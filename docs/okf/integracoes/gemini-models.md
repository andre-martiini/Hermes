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
- **Flex inference:** chamadas de bastidor e tolerantes a latência passam pelo wrapper `generate_content_logged`, que pode enviar `service_tier=flex` para reduzir custo. O comportamento é controlado por env:
  - `HERMES_GEMINI_FLEX_ENABLED=0` desativa Flex globalmente.
  - `HERMES_GEMINI_FLEX_FEATURES=feature.a,feature.b` substitui a allowlist padrão; `*` ativa para todas as chamadas logadas.
  - `HERMES_GEMINI_FLEX_DISABLED_FEATURES=feature.a` remove features específicas.
  - `GEMINI_FLEX_FALLBACK_TO_STANDARD=0` desativa fallback automático para Standard quando Flex retorna 429/503.
  - `GEMINI_FLEX_TIMEOUT_MS` ajusta timeout por requisição Flex (padrão 600000 ms).
- **Tratamento de erros:**
  - `503 UNAVAILABLE`: alta demanda no modelo lite específico. Pausar e tentar novamente, ou trocar temporariamente pelo Pro correspondente se urgente.
  - `403 PERMISSION_DENIED` (vazamento de API key): garantir que as chaves fiquem em arquivos `.env`, nunca hardcoded em `.py`/`.tsx` que possam ir para produção ou repositório público.

## Armazenamento de chaves

- Arquivos `.env` locais usados em `Hermes-Bot/` e na raiz do projeto.
- `.gitignore` deve incluir explicitamente `.env` e `.env.local` para prevenir vazamentos.
