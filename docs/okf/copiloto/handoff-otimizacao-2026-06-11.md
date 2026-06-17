---
type: handoff
title: Handoff — Otimização do Copiloto Hermes (continuação)
description: Estado da otimização de latência, custo e autonomia do Copiloto Hermes após o commit d5bf62c, com pendências e backlog priorizado.
resource: functions/main.py
tags: [hermes, copiloto, performance, custo, rag]
timestamp: 2026-06-11T19:59:14-03:00
---

# Handoff — Otimização do Copiloto Hermes (continuação)

**Último commit:** `d5bf62c` — "perf: acelerar copiloto e reduzir consumo de tokens" (em `main`, deploy via CI).

**Contexto:** três frentes pedidas — (1) acelerar a resposta do copiloto, (2) reduzir custo de tokens, (3) tornar o sistema mais autônomo/inteligente. A primeira leva foi implementada e publicada; este documento lista o que falta, em ordem de prioridade.

## O que já foi feito (commit d5bf62c)

- Bug do cache de POPs corrigido (`_match_pop_directives` em `functions/main.py` re-baixava a coleção em todo miss).
- Cache de 5 min para catálogos `sistemas_detalhes` e `unidades` (`_cached_collection_list` em main.py; `_AREAS_VALIDAS_CACHE` em hermes_core_logic.py).
- Busca de memórias (`_find_similar_memory_nodes`) migrada para `find_nearest` nativo do Firestore, com pré-filtro `tipo in [regra_global, fato_isolado]` e fallback para varredura local de 200 docs se índice/vetores não existirem.
- Embeddings agora gravados como `Vector` (antes listas simples → fora do índice vetorial, invisíveis ao `find_nearest`). Corrigido em main.py (memórias, SIPAC) e knowledge_graph.py (nós do grafo, indice_artefatos).
- 3 índices vetoriais novos de `knowledge_nodes` em `firestore.indexes.json` (embedding; tipo+embedding; area_tematica+embedding), deployados pelo CI.
- System prompt do `askCopilotoHermes` enxuto: protocolos raros (slides, formulários, relatórios, reagendamento em lote, diagramas) só entram com keywords no prompt + histórico (`_protocolo_ativo`, normalização via `_normalize_pop_text`). ~3k tokens economizados por chamada típica.
- Ferramentas raras (SIPAC ×3, gerar_imagem, buscar_e_analisar_email, gerar_relatorio, gerar_rascunho_formulario, reagendamento em lote) declaradas condicionalmente pelo mesmo gating.
- `preparar_remocao_horarios_em_lote` agora declarada ao modelo web (antes só citada no prompt).
- Roteador de intenção de correção usando `GEMINI_ROUTING_MODEL` (flash-lite) em vez de gemini-3.5-flash.
- Smalltalk roteado para `GEMINI_BALANCED_MODEL`.
- Telemetria `log_gemini_usage` em todas as chamadas do copiloto web (features: `copilot_web`, `copilot_web_fallback`, `copilot_intent_router`, `copilot_file_ingestion`); agregado diário em `system_usage/gemini/daily/{YYYY-MM-DD}`.
- Watchdog `relatorio_diario_custo_gemini` (20h30 BRT): resumo de custo no Telegram + alerta de orçamento.
- Status progressivo: backend grava `copilotStatus` em `sessoes_copiloto/{id}`; frontend (HermesCopilotoDrawer + HermesGlobalChat) exibe via onSnapshot durante o loading.

## Pendente 1 — Backfill dos embeddings legados (urgente, ~5 min)

Converter embeddings existentes de lista simples → tipo `Vector` em `knowledge_nodes` e `indice_artefatos`. Sem isso, documentos antigos ficam invisíveis ao vector search (busca de memórias cai no fallback lento; RAG não enxerga artefatos antigos do grafo/SIPAC).

```bash
python scripts/backfill_embeddings_vector.py
```
Idempotente (pula docs já convertidos), imprime contagens por coleção. Bloqueado anteriormente por ser mutação em massa em produção — requer autorização explícita.

**Validação pós-backfill:** perguntar algo ao copiloto que acione memórias e confirmar nos logs de `askCopilotoHermes` que NÃO aparece `[Memoria] find_nearest indisponível, usando varredura local`.

## Pendente 2 — Verificações pós-deploy (~15 min)

1. Workflow "Deploy Hermes (Firebase)" do commit `d5bf62c` ficou verde no GitHub Actions.
2. Os 3 índices vetoriais de `knowledge_nodes` saíram de "Building" para "Enabled" no console Firestore.
3. Testes no app: mensagem comum (status progressivo), "Crie uma apresentação sobre X" (protocolo de slides), "Faça um formulário de pesquisa" (protocolo de formulário), "Tira o horário de todas as ações de hoje" (card de remoção em lote), smalltalk ("bom dia").
4. `system_usage/gemini/daily/{hoje}` acumulando tokens/custo.
5. Resumo de custo chegando no Telegram às 20h30 BRT — se não chegar, checar `ALLOWED_TELEGRAM_CHAT_ID` ou campos `telegram_chat_id`/`allowed_telegram_chat_id` em `system/api_keys`.
6. (Opcional) criar `system/cost_controls` com `{ daily_budget_usd: <valor> }` (default $5.00).

## Pendente 3 — Riscos do gating a observar

O gating de protocolos/ferramentas usa keywords sobre `prompt + últimas 6 mensagens` (`_protocolo_ativo` em `functions/main.py`).

- Pedido sem nenhuma keyword da lista → protocolo não entra, modelo improvisa sem o formato `[PRESENTATION]`/`[FORM]` esperado pelo frontend. Correção: adicionar a keyword faltante ao gate (`_gate_slides`, `_gate_formularios` etc.).
- Mesma lógica para tools: se o copiloto negar ter uma ferramenta de e-mail/imagem/SIPAC, checar keywords dos blocos `static_tools.append(...)`.
- Histórico só carrega com `session_id` — primeira mensagem de sessão nova depende só do prompt.

## Backlog — próximas melhorias (em ordem de valor)

### Briefing diário proativo
Scheduled function (~7h BRT): resumo do dia (ações com `data_limite` hoje/atrasadas em `tarefas`, agenda via `hermes_calendar_tools.py`, e-mails importantes se viável). Gravar em `briefings_diarios/{data}`, enviar via Telegram (`_send_telegram_message`, mesmo padrão do watchdog de custo). Usar `GEMINI_BALANCED_MODEL`.

### Streaming real
`askCopilotoHermes` hoje é callable (resposta única, cliente espera até 240s). Migrar para HTTP+SSE com `client.models.generate_content_stream`, ou gravar resposta parcial no Firestore a cada N tokens (a infra de listener via `copilotStatus` já mostra o caminho).

### Memória consolidada no prompt
Manter um "perfil sintetizado" curto (gerado pelo job `consolidar_memorias_copiloto`, já roda às 4h) e injetá-lo direto no system prompt; busca vetorial só para perguntas explicitamente sobre memórias.

### Simplificar caminho do Telegram
Webhook do Telegram delega ao copiloto web via HTTP interno (`_call_web_callable`/`_run_web_copilot_engine` em hermes_core_logic.py) — duas Cloud Functions encadeadas por mensagem. Avaliar chamada direta da lógica (import) em vez de HTTP.

### Limpezas menores
- `_old_function_map` em `askCopilotoHermes` é código morto — remover.
- `gerarResumoSaude`/`gerarResumoFinanceiro` e outras chamadas usam `gemini-3.5-flash` hardcoded — migrar para os tiers de `gemini_cost_controls.py` se o custo continuar alto (decidir por dados de `system_usage/gemini/daily`).
- `find_nearest` em `consultar_historico_acoes`/busca do grafo (main.py, ~linha 10660) usa `nd.get("__vector_distance__")`, que não funciona no SDK Python (score sempre 0.0) — trocar por `distance_result_field`, como feito em `_find_similar_memory_nodes`.
- Decidido NÃO fazer: context caching explícito do Gemini (pouco ganho após o enxugamento do prompt; reavaliar só se a telemetria mostrar custo de input ainda dominante).

## Como medir o resultado (após 2-3 dias de uso)

- `system_usage/gemini/daily/{data}`: comparar `estimated_usd`, `tokens.input` e distribuição por `features`. Antes das mudanças não havia medição do copiloto web — os primeiros dias estabelecem o baseline já otimizado.
- Logs `[PERF] web.askCopiloto.complete` (Cloud Logging): campo `steps` mostra duração de cada fase (bootstrap, prompt_build, first_model_response, tool_roundtrip...). Ganhos de cache aparecem em `web.bootstrap` e `web.session_context`.
