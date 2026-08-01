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

- Arquivos `.env` locais usados na raiz do projeto e em subserviços (ex.: `hermes-voice-bridge/`).
- `.gitignore` deve incluir explicitamente `.env` e `.env.local` para prevenir vazamentos.

## A/B test: GPT-5.6 Luna vs. roteador de intenção Gemini (2026-08)

Após o corte de preço de 80% no GPT-5.6 Luna (30/jul/2026), que o deixou mais
barato que o `gemini-3.5-flash-lite` nos dois lados (input e output) e com
nota de inteligência superior (Artificial Analysis Intelligence Index 46 vs
36), foi adicionado um provider mínimo da OpenAI para testar o Luna em uma
feature real de alto volume e baixo risco: o roteador de intenção de
`askCopilotoHermes` (main.py, bloco `# --- ROTEADOR DE INTENÇÃO`).

- **Provider:** `functions/llm_providers/openai_provider.py` — cliente fino
  para a Responses API, com telemetria de custo espelhando
  `gemini_cost_controls.log_gemini_usage` (grava em
  `system_usage/openai/daily/<data>`).
- **Chave:** campo `openai_api_key` no doc Firestore `system/api_keys`
  (mesmo padrão de `claude_api_key`/`gemini_api_key`).
- **Ativação do A/B:** env var `HERMES_AB_LUNA_INTENT_ROUTER_PCT` (0-100).
  Define a % de chamadas do roteador de intenção desviadas para o Luna em vez
  do Gemini. Padrão de operação no código: **10%** (rollout inicial
  conservador, definido em 01/08/2026 após a chave `openai_api_key` ser
  cadastrada em `system/api_keys`). Pode ser ajustado sem novo deploy do
  código setando essa env var no ambiente das Cloud Functions; setar `0`
  desliga o A/B por completo.
- **Esforço de raciocínio:** fixo em `low` nessa chamada — Luna não se
  beneficia proporcionalmente de esforço maior, e a tarefa é uma classificação
  binária (`CORRECAO`/`NORMAL`).
- **Sem fallback cruzado:** se o provider sorteado falhar, a chamada é
  fail-open (sem hint de correção) igual ao comportamento anterior — não há
  novo fallback entre Luna e Gemini na mesma requisição, para não misturar
  os números do A/B.
- **Comparação:** os custos de cada provider ficam em coleções paralelas
  (`system_usage/gemini` e `system_usage/openai`), agregáveis por dia/feature
  para decidir se vale expandir o Luna para mais chamadas do Hermes.
