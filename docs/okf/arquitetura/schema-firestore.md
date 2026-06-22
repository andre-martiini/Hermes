---
type: reference
title: Schema do Firestore
description: Coleções do Firestore usadas pelo Hermes, agrupadas por domínio, com campos principais, quem escreve em cada uma e suas relações.
resource: types.ts
tags: [hermes, okf, firestore, schema, arquitetura]
timestamp: 2026-06-17T00:00:00Z
---

# Schema do Firestore

Este documento mapeia as coleções do Firestore usadas em produção. A maioria dos modelos correspondentes está tipada em `types.ts` (raiz do repo). Coleções sem interface dedicada têm estrutura dinâmica definida diretamente no código das Cloud Functions.

Convenção: "Escreve" lista quem grava na coleção (frontend via SDK, Cloud Function específica, scheduler). "Relações" lista referências por ID a outras coleções.

## Núcleo: tarefas

### `tarefas`
Núcleo de toda a aplicação — ações/tarefas do usuário.

- **Campos-chave:** `titulo`, `projeto`, `area_tematica`, `data_inicio`, `data_limite`, `data_conclusao`, `status` (`em andamento`\|`stand-by`\|`concluído`), `execution_lane`, `acompanhamento[]`, `chat_history[]`, `plano_acao[]`, `artefatos_kg[]`, `kg_tags[]`, `concept_node_id`, `horario_inicio`/`horario_fim`, `reminders[]`, `origem` (`manual`\|`audio`\|`whatsapp`), `sync_status`, `knowledge_item_ids[]`.
- **Escreve:** frontend (CRUD direto); `run_full_sync` (sync Google Calendar); `on_tarefa_created_kg`/`on_tarefa_concluida_kg` (grafo); `on_processo_updated` (SIPAC); callables diversas do Copiloto.
- **Relações:** `concept_node_id` → `knowledge_nodes`; `knowledge_item_ids[]` → `conhecimento`; subcoleção implícita em `sessoes_copiloto`.
- **Índice:** `reminder_sent` + `reminder_at` (ASC).

## Conhecimento e RAG

### `knowledge_nodes`
Nós conceituais do grafo de conhecimento (Fase 2 — cristalização). Campos: `titulo`, `area_tematica`, `embedding` (vector 768-dim), `n_tasks`, `task_ids[]`, `resumo`, `data_criacao`/`data_atualizacao`. Escrito por `on_tarefa_concluida_kg` e pelo pipeline de memórias do Copiloto (`_save_memory_node`, `consolidar_memorias_copiloto`). Índices vetoriais: `embedding`; `tipo+embedding`; `area_tematica+embedding`.

### `knowledge_edges`
Arestas que ligam tarefas concluídas a nós conceituais: `task_id`, `node_id`, `peso_semantico` (0–1), `data_conclusao` (marco do time decay, λ=0.001). Escrito por `on_tarefa_concluida_kg`.

### `indice_artefatos`
Índice vetorial unificado (artefatos de tarefas + acervo global) para RAG híbrido: `nome`, `url`, `tipo_mime`, `resumo_semantico`, `embedding` (768-dim), `tags[]`, `origem` (`tarefa`\|`acervo`), `task_id`/`acervo_id`, `indexed_at`, `file_search`. Escrito por `process_vectorization`, `processar_artefato_kg`, `monitorar_acervo_global`.

### `acervo_global`
Arquivos avulsos da "Pasta de Deságue" (Google Drive) indexados no RAG: `nome`, `url`, `tipo_mime`, `drive_file_id`, `resumo_semantico`, `tags[]`, `status_indexacao`, `indexed_at`. Escrito por `monitorar_acervo_global`.

### `conhecimento`
Itens de conhecimento (documentos, links, notas) — base RAG geral, com hierarquia de pastas: `titulo`, `url_drive`, `tipo_arquivo`, `texto_bruto`/`resumo_tldr`, `tags[]`, `categoria`, `area_tematica`, `base_id`, `origem`, `parent_id`/`is_folder`. Escrito pelo frontend e por `on_arquivo_adicionado`, `findSimilarKnowledge`, `on_knowledge_item_updated`. Relação: `base_id` → `knowledge_bases`; referenciado por `tarefas.knowledge_item_ids`.

### `knowledge_bases`
Bases de conhecimento personalizadas para RAG seletivo: `nome`, `descricao`, `tipo`, `configuracao_rag` (`incluir_diarios`, `incluir_manual`, `categorias_vinculadas`, `tags_vinculadas`). Escrito pelo frontend; consumido por `retrieve_personalized_rag_context`.

### `pops_diretrizes` e `conhecimento_mestre`
Procedimentos Operacionais Padrão e diretrizes gerais consultados pelo gating de protocolos do Copiloto (`_match_pop_directives`). `conhecimento_mestre` é predecessor menos usado.

### `processos_conhecimento`
Documentos vetorizados por `process_vectorization` — uso decrescente, mantido por compatibilidade.

## Copiloto e jobs de IA assíncronos

### `sessoes_copiloto` (+ subcoleção `mensagens`)
Sessões de conversa multi-turno com o Copiloto: `userId`, `lastMessageAt`, `task_id`, `session_id`; subcoleção `sessoes_copiloto/{id}/mensagens` guarda o histórico (`ChatMessage`: role, content, timestamp). Escrito por `askCopilotoHermes`. Índice: `userId+lastMessageAt` (DESC).

### `usuarios`
Perfis de IA por usuário (preferências, sinais aprendidos): criado por `_bootstrap_user_ai_profile`, atualizado por `_save_user_profile_signal`.

### `correcoes_pendentes`
Fila de correções a aplicar em tarefas, detectadas por callables diversas; processada em lote por `processar_correcoes_pendentes` (scheduler, a cada 60 min).

### `long_transcriptions`
Transcrições de áudio longo via Google Speech-to-Text: `userId`, `createdAt`. Criado por `transcreverAudio` e pelo trigger de Storage `on_long_transcription_uploaded`. Índice: `userId+createdAt` (DESC).

### `quality_logs`
Logs de qualidade/feedback de respostas geradas pelo sistema.

## Pessoas, projetos e bolsistas

### `perfil_pessoas`
Contatos, bolsistas e colaboradores: `nome`, `email`, `telefone`, `cpf`/`rg`, `dados_bancarios`, `lattes`, `origem` (`manual`\|`google_contacts`\|`extracao_ia`), `google_contact_id`, `resumo_ia`. Escrito pelo frontend, por `sync_google_contacts`, `generate_contact_summary`, e por extratores de menções em tarefas (`knowledge_graph.py`).

### `vinculos_projeto`
Vínculo de bolsista/colaborador a um projeto: `pessoa_id`, `projeto_id`, `tipo_bolsa_id`, `percentual_recebimento`, `funcao`, `status`, `documentos`, `valor_bolsa_mensal_atual`. Relações: → `perfil_pessoas`, → `projetos`, → `tipo_bolsas`.

### `projetos`
Projeto/departamento com orçamento (`orcamento`: custeio, capital, bolsas) e token de registro público (`public_registration_token`) usado pelos portais públicos de `security_portals.py`.

### `tipo_bolsas`
Catálogo de modalidades de bolsa: `nome_modalidade`, `valor_integral`, `valor_parcial`.

### `interacoes_pessoas`
Histórico de interações por pessoa: `pessoa_id`, `tipo` (`mencao_tarefa`\|`mencao_diario`\|`reuniao`\|`manual`\|`mencao_copiloto`), `data`, `descricao`. Escrito por extratores de menções (`on_tarefa_written_extract_people`) e pelo Copiloto.

## Financeiro

### `finance_transactions`
Transações financeiras: `description`, `amount`, `date`, `sprint`, `category`, `originalTaskId`, `google_message_id`, `status` (`active`\|`deleted`), `origin` (`internal`\|`external`). Escrito pelo frontend, por `sync_pix_emails`, pelo portal público de finanças e por `sync_gmail_bills_callable`.

### `fixed_bills` / `bill_rubrics`
Contas a pagar fixas/recorrentes e seus templates de rubrica. `fixed_bills`: `description`, `amount`, `dueDay`, `month`/`year`, `pixCode`, `isPaid`, `rubricId` → `bill_rubrics`. Sincronizado por `sync_boletos_gmail`.

### `income_entries` / `income_rubrics`
Receitas e seus templates de rubrica. `income_entries`: `description`, `amount`, `day`/`month`/`year`, `rubricId` → `income_rubrics`, `service_id` → `servicos`, `isReceived`. Sincronizado por `sync_pix_emails`.

### `finance_settings` / `finance_goals`
Configurações globais (orçamento mensal, reserva de emergência, categorias) e metas financeiras (`targetAmount`, `currentAmount`, `status`).

### `servicos`
Contratos/serviços (freelance, consultoria): `titulo`, `cliente`, `status`, `tipo_contrato`, `valor_total`, `parcelas[]` (`ParcelaServico`), `categoria_financeira`, `base_id` → `knowledge_bases`. Referenciado por `income_entries.service_id`.

## Saúde

### `health_exercise_logs`
Log diário (`id` = `YYYY-MM-DD`): exercícios (`pushups`, `pullups`, `plank`, `squats`, `walk`...), `calories`, `heartRate`, `sleep`, `pain`.

### `health_weights`
Histórico de peso por dia: `date`, `weight`, `fatPercentage`, `muscleMass`.

### `health_daily_habits`
Checklist diário de hábitos (`noSugar`, `noAlcohol`, `workout`, `eatUntil18`...).

### `health_telegram_reminders`
Reminders de saúde enviados via Telegram: `title`, `time`, `daysOfWeek[]`, `category` (`spine`\|`walking`\|`nutrition`\|`pain`\|`custom`), `last_sent_date`.

### `exames`
Exames e consultas médicas: `titulo`, `doutor_local`, `resultados`, `data`, `tipo` (`exame`\|`consulta`), `pool_dados[]`.

## Sistema, operacional e integrações

| Coleção | Representa | Escreve |
|---|---|---|
| `notificacoes` | Notificações do app, espelhadas no Telegram | `emit_notification_backend`, trigger `on_notificacao_created` |
| `system_reminders` | Cache para evitar duplicar reminders já enviados | `check_and_send_reminders` |
| `relatorios` | Relatórios gerados (PGD e resumos) | `salvarRelatorioNoDrive`, callables de resumo |
| `google_calendar_events` | Eventos do Google Calendar sincronizados | `sync_google_calendar`, `run_full_sync` |
| `sipac_processos` | Processos SIPAC sincronizados (scraper externo via PubSub) | trigger `on_processo_updated` |
| `whatsapp_outbox` | Fila de mensagens WhatsApp agendadas | `schedule_whatsapp_message` (tools) |
| `whatsapp_messages` | Mensagens capturadas pelo microsserviço WhatsApp — ver [Integração WhatsApp](/docs/okf/integracoes/whatsapp.md) | microsserviço `services/whatsapp-capture` |
| `system/api_keys`, `system/settings`, `system/config`, `system/sync`, `system/google_credentials`, `system/file_search`, `system/cost_controls` | Documentos de configuração e estado global, na coleção `system` | admin/setup scripts; `on_sync_request`; `start_file_indexing` |
| `system_usage/gemini/daily/{data}` | Telemetria diária de uso/custo da API Gemini | `log_gemini_usage` (`gemini_cost_controls.py`) |
| `idempotency` | Deduplicação de requisições (TTL via `expires_at`) | `core/idempotency.py` |
| `telegram_sessions` | Sessões ativas de Telegram (TTL via `expires_at`) | `core/session.py` |
| `whitelist` | Chat IDs de Telegram autorizados | admin (`hermes_core_logic.py`) |
| `configuracoes`, `public_configs`, `unidades` | Configurações de app e unidades organizacionais | frontend / admin |

## Convenções gerais

- Datas são strings ISO 8601, exceto `createdAt` em algumas coleções de jobs que usa `Timestamp` nativo do Firestore.
- Embeddings usam o tipo `Vector` nativo do Firestore (768 dimensões, `gemini-embedding-001`) — gravar como lista simples deixa o documento invisível ao `find_nearest`.
- IDs de documento costumam ser auto-gerados, exceto séries diárias (`health_*`, `system_usage/gemini/daily/*`), que usam `YYYY-MM-DD` como ID.
