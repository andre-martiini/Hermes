# Handoff — Otimização do Copiloto Hermes (continuação)

**Data:** 2026-06-11
**Último commit:** `d5bf62c` — "perf: acelerar copiloto e reduzir consumo de tokens" (pushed para `main`, deploy via CI)
**Contexto:** O André pediu 3 frentes: (1) acelerar a resposta do copiloto, (2) reduzir custo de tokens, (3) tornar o sistema mais autônomo/inteligente. A primeira leva de otimizações foi implementada e publicada. Este documento lista o que **falta fazer**, em ordem de prioridade.

---

## ✅ O que já foi feito (commit d5bf62c) — para contexto

- Bug do cache de POPs corrigido (`_match_pop_directives` em `functions/main.py` re-baixava a coleção em todo miss).
- Cache de 5 min para catálogos `sistemas_detalhes` e `unidades` (`_cached_collection_list` em main.py; `_AREAS_VALIDAS_CACHE` em hermes_core_logic.py).
- Busca de memórias (`_find_similar_memory_nodes`) migrada para `find_nearest` nativo do Firestore com pré-filtro `tipo in [regra_global, fato_isolado]` e **fallback** para varredura local de 200 docs se o índice/vetores não existirem.
- Embeddings agora gravados como `Vector` (antes eram listas simples → ficavam FORA do índice vetorial e invisíveis ao `find_nearest`). Gravadores corrigidos em main.py (memórias, SIPAC) e knowledge_graph.py (nós do grafo, indice_artefatos).
- 3 índices vetoriais novos de `knowledge_nodes` em `firestore.indexes.json` (embedding; tipo+embedding; area_tematica+embedding) — deployados pelo CI.
- System prompt do `askCopilotoHermes` enxuto: protocolos raros (slides, formulários, relatórios, reagendamento em lote, diagramas) só entram quando keywords aparecem no prompt + histórico (função `_protocolo_ativo`, normalização via `_normalize_pop_text`). ~3k tokens economizados por chamada típica.
- Ferramentas raras (SIPAC ×3, gerar_imagem, buscar_e_analisar_email, gerar_relatorio, gerar_rascunho_formulario, reagendamento em lote) declaradas condicionalmente pelo mesmo gating.
- `preparar_remocao_horarios_em_lote` agora declarada ao modelo web (era citada no prompt mas não estava na lista de tools).
- Roteador de intenção de correção: `GEMINI_ROUTING_MODEL` (flash-lite) em vez de gemini-3.5-flash.
- Smalltalk (saudações/agradecimentos curtos sem anexo/tarefa) roteado para `GEMINI_BALANCED_MODEL`.
- Telemetria `log_gemini_usage` em TODAS as chamadas do copiloto web (features: `copilot_web`, `copilot_web_fallback`, `copilot_intent_router`, `copilot_file_ingestion`). Agregado diário em `system_usage/gemini/daily/{YYYY-MM-DD}`.
- Watchdog `relatorio_diario_custo_gemini` (scheduled, 20h30 BRT): resumo de custo no Telegram + alerta de orçamento.
- Status progressivo: backend grava `copilotStatus` no doc da sessão (`sessoes_copiloto/{id}`); frontend (HermesCopilotoDrawer + HermesGlobalChat) exibe via onSnapshot durante o loading.

---

## 🔴 PENDENTE 1 — Backfill dos embeddings legados (URGENTE, 5 min)

**O que é:** converter os embeddings já existentes de lista simples → tipo `Vector` em `knowledge_nodes` e `indice_artefatos`. Sem isso, os documentos antigos continuam invisíveis ao vector search (a busca de memórias cai no fallback lento e o RAG não enxerga artefatos antigos do grafo/SIPAC).

**Como fazer:** na raiz do projeto (usa `firebase_service_account_key.json` da raiz):
```
python scripts/backfill_embeddings_vector.py
```
O script é idempotente (pula docs já convertidos) e imprime contagens por coleção.

**Por que não foi feito:** o executor anterior foi bloqueado pelo classificador de permissões por ser mutação em massa em produção; o André precisa rodar ou autorizar explicitamente.

**Validação pós-backfill:** fazer uma pergunta ao copiloto que acione memórias e conferir nos logs da function `askCopilotoHermes` que NÃO aparece `[Memoria] find_nearest indisponível, usando varredura local`.

---

## 🟡 PENDENTE 2 — Verificações pós-deploy (15 min)

1. Confirmar que o workflow "Deploy Hermes (Firebase)" do commit `d5bf62c` ficou verde (GitHub Actions).
2. Confirmar no console do Firestore que os 3 índices vetoriais de `knowledge_nodes` saíram de "Building" para "Enabled".
3. Testar no app:
   - Mensagem comum → resposta + status progressivo aparecendo ("Analisando sua solicitação...", "Executando: ...").
   - "Crie uma apresentação sobre X" → protocolo de slides ainda funciona (gating).
   - "Faça um formulário de pesquisa" → protocolo de formulário funciona.
   - "Tira o horário de todas as ações de hoje" → card de remoção em lote funciona (tool recém-declarada).
   - Smalltalk ("bom dia") → responde normal (modelo barato; ver log `[Copiloto] Smalltalk detectado`).
4. Conferir que `system_usage/gemini/daily/{hoje}` está acumulando tokens/custo após algumas mensagens.
5. Às 20h30 BRT, conferir se o resumo de custo chegou no Telegram. Se não chegar: o watchdog procura o chat id em (a) env `ALLOWED_TELEGRAM_CHAT_ID`, (b) campos `telegram_chat_id` ou `allowed_telegram_chat_id` do doc `system/api_keys`. Se nenhum existir, gravar o chat id do André em `system/api_keys.telegram_chat_id`.
6. (Opcional) Criar doc `system/cost_controls` com `{ daily_budget_usd: <valor> }` — default é $5.00.

---

## 🟡 PENDENTE 3 — Riscos do gating a observar (primeiros dias)

O gating de protocolos/ferramentas usa keywords sobre `prompt + últimas 6 mensagens` (função `_protocolo_ativo` dentro de `askCopilotoHermes`, `functions/main.py`). Possíveis falhas e correção:

- Se o usuário pedir slides/formulário/relatório/diagrama com fraseado que não contém nenhuma keyword, o protocolo não entra e o modelo improvisa sem o formato `[PRESENTATION]`/`[FORM]` que o frontend espera. **Correção:** adicionar a keyword que faltou à lista do gate correspondente (buscar `_gate_slides`, `_gate_formularios` etc. em main.py).
- Mesma lógica para tools: se o copiloto disser "não tenho essa ferramenta" para e-mail/imagem/SIPAC, conferir as keywords dos blocos `static_tools.append(...)`.
- O histórico só carrega com `session_id` — primeira mensagem de sessão nova depende só do prompt.

---

## 🟢 BACKLOG — Próximas melhorias recomendadas (em ordem de valor)

### 3.1 Briefing diário proativo (autonomia — recomendado como próximo)
Scheduled function (~7h BRT) que monta resumo do dia: ações com `data_limite` hoje/atrasadas (coleção `tarefas`), agenda do dia (helpers em `hermes_calendar_tools.py`), e-mails importantes se viável. Gravar em coleção `briefings_diarios/{data}` e enviar via Telegram (`_send_telegram_message` de hermes_core_logic, mesmo padrão do watchdog `relatorio_diario_custo_gemini`). Usar `GEMINI_BALANCED_MODEL` para sintetizar.

### 3.2 Streaming real (latência percebida)
Hoje `askCopilotoHermes` é callable (resposta única no fim; cliente espera até 240s). Migrar para endpoint HTTP com SSE usando `client.models.generate_content_stream`, ou — mais simples — gravar a resposta parcial no Firestore a cada N tokens e o frontend renderizar via onSnapshot (a infra de listener já existe; o campo `copilotStatus` mostrou o caminho).

### 3.3 Memória consolidada no prompt (custo + latência)
Em vez de busca vetorial por turno, manter um "perfil sintetizado" curto (gerado pelo job `consolidar_memorias_copiloto`, que já roda às 4h) e injetá-lo direto no system prompt. A busca vetorial ficaria só para perguntas explicitamente sobre memórias.

### 3.4 Simplificar o caminho do Telegram
O webhook do Telegram delega ao copiloto web via HTTP interno (`_call_web_callable` / `_run_web_copilot_engine` em hermes_core_logic.py) — duas Cloud Functions encadeadas por mensagem. Avaliar chamada direta da lógica (import) em vez de HTTP.

### 3.5 Limpezas menores
- `_old_function_map` em `askCopilotoHermes` é código morto (dict duplicado nunca usado) — remover.
- `gerarResumoSaude`/`gerarResumoFinanceiro` e dezenas de outras chamadas usam `gemini-3.5-flash` hardcoded — migrar para os tiers de `gemini_cost_controls.py` caso o custo continue alto (ver `system_usage/gemini/daily` para decidir por dados).
- O caminho `find_nearest` em `consultar_historico_acoes`/busca do grafo (main.py, ~linha 10660) usa `nd.get("__vector_distance__")` que não funciona no SDK Python — o score sempre vem 0.0. Trocar por `distance_result_field` como foi feito em `_find_similar_memory_nodes`.
- Decidido NÃO fazer: context caching explícito do Gemini (pouco ganho após o enxugamento do prompt; reavaliar apenas se a telemetria mostrar custo de input ainda dominante).

---

## Como medir o resultado (após 2–3 dias de uso)

- `system_usage/gemini/daily/{data}`: comparar `estimated_usd`, `tokens.input` e a distribuição por `features`. Antes das mudanças NÃO havia medição do copiloto web — os primeiros dias estabelecem o baseline já otimizado.
- Logs `[PERF] web.askCopiloto.complete` (Cloud Logging): campo `steps` mostra a duração de cada fase (bootstrap, prompt_build, first_model_response, tool_roundtrip...). Os ganhos de cache aparecem em `web.bootstrap` e `web.session_context`.
