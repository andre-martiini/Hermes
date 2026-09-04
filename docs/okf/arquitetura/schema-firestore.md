---
type: reference
title: Schema do Firestore
description: Coleções do Firestore usadas pelo Hermes, agrupadas por domínio, com campos principais, quem escreve em cada uma e suas relações.
resource: types.ts
tags: [hermes, okf, firestore, schema, arquitetura]
timestamp: 2026-08-22T00:00:00-03:00
---

# Schema do Firestore

Este documento mapeia as coleções do Firestore usadas em produção. A maioria dos modelos correspondentes está tipada em `types.ts` (raiz do repo). Coleções sem interface dedicada têm estrutura dinâmica definida diretamente no código das Cloud Functions.

Convenção: "Escreve" lista quem grava na coleção (frontend via SDK, Cloud Function específica, scheduler). "Relações" lista referências por ID a outras coleções.

## Núcleo: tarefas

### `tarefas`
Núcleo de toda a aplicação — ações/tarefas do usuário.

- **Campos-chave:** `titulo`, `projeto`, `area_tematica`, `data_inicio`, `data_limite`, `data_conclusao`, `status` (`em andamento`\|`stand-by`\|`concluído`), `execution_lane`, `acompanhamento[]`, `chat_history[]`, `plano_acao[]`, `artefatos_kg[]`, `kg_tags[]`, `concept_node_id`, `horario_inicio`/`horario_fim`, `reminders[]`, `origem` (`manual`\|`audio`\|`whatsapp`), `sync_status`, `knowledge_item_ids[]`, `email_link_optout` (opt-out do vínculo automático de e-mail por IA — ver `email_action_linker.py`), `whatsapp_vinculos[]` (contatos/grupos de WhatsApp vinculados manualmente à ação — matching determinístico usado por `whatsapp_ingest.py`, ver §3 de `docs/okf/integracoes/whatsapp.md`).
- **Entradas ricas do diário (`acompanhamento[].nota`):** além de texto livre, o frontend entende o envelope `TIPO::JSON::{...}` (`src/utils/diaryEntries.ts`) para `LINK`, `CONTACT`, `FILE` e `EMAIL` (esta última também escrita pelo backend em `email_action_linker.py`, payload `{n: assunto, v: link Gmail, s: remetente, r: resumo}`).
- **Escreve:** frontend (CRUD direto); `run_full_sync` (sync Google Calendar); `on_tarefa_created_kg`/`on_tarefa_concluida_kg` (grafo); `on_processo_updated` (SIPAC); callables diversas do Copiloto.
- **Relações:** `concept_node_id` → `knowledge_nodes`; `knowledge_item_ids[]` → `conhecimento`; subcoleção implícita em `sessoes_copiloto`.
- **Índice:** `reminder_sent` + `reminder_at` (ASC).

## Metas e estratégia pessoal

### `estrategia_pessoal`
Objetivos/metas estratégicas pessoais do usuário (equivalente a metas de PGD/plano de gestão, mas de escopo pessoal). Campos: `userId`, `pilar` (`carreira`\|`financas`\|`saude`\|`intelectual`\|`estilo_vida`), `objetivoMacro`, `tipoMeta` (`absoluta`\|`relativa_qualitativa`), `metricaAlvo` (`valorInicial`, `valorAtual`, `valorObjetivo`, `unidade`), `historicoMetrica[]`, `indicadoresSucesso[]`, `marcos[]`, `diretrizesDerivadas[]`, `status` (`ativo`\|`concluido`\|`revisar`). Escrito pelo frontend (`StrategyDashboardView.tsx`), pelo refinamento por IA (`estrategia_pessoal_refinar`) e pelas tools de chat do Copiloto e do Godmode (CRUD compartilhado em `strategy_tools.py`, usado por `main.py:10296-10520` e `godmode.py`). Lido também pelo planejador de notificações de IA (ver `scheduled_notifications` abaixo). Relação: `tarefas.estrategia_objetivo_id`/`estrategia_indicador_id` apontam de volta para cá.

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
Sessões de conversa multi-turno com o Copiloto: `userId`, `lastMessageAt`, `task_id`, `session_id`, `channel` (`"telegram"` quando originada lá), `copilotScope`; subcoleção `sessoes_copiloto/{id}/mensagens` guarda o histórico (`ChatMessage`: role, content, timestamp, `source` — `telegram`\|`telegram_callback`\|`web_global`\|`web_drawer`\|`web_task_view`\|`voice_web`; ausente nos writes de `askCopilotoHermes` e em sessões antigas). Escrito por `askCopilotoHermes` e diretamente pelo frontend (`HermesGlobalChat.tsx`, `HermesCopilotoDrawer.tsx`, `TaskExecutionView.tsx`). Índice: `userId+lastMessageAt` (DESC).

### `sessoes_godmode` (+ subcoleção `mensagens`)
Mesmo formato de `sessoes_copiloto` (`userId`, `lastMessageAt`, `titulo`; subcoleção `mensagens` com `role`/`content`/`timestamp`), mas para o modo Godmode (`godmode.py:askHermesGodmode`, Claude em vez de Gemini). Ambas as coleções de sessão são lidas por `gerar_diario_pessoal` (`personal_diary.py`) para compor o diário do dia — conversas com o Godmode também alimentam o ciclo diário → `ai_profile.personalidade`.

### `usuarios`
Perfis de IA por usuário: criado por `_bootstrap_user_ai_profile`, sinais de prompt atualizados por `_save_user_profile_signal` (`ai_profile.historico_deduzido`, rolling últimos 10). Campo `ai_profile.personalidade` — traços/estilo/rotinas destilados semanalmente do diário pessoal por `consolidar_personalidade` (`personal_diary.py`), com `personalidade_historico[]` (últimas 6 versões). Lido por `_format_ai_profile_for_prompt` (copiloto web/Godmode) e `context.py:_format_user_profile` (ponte de voz) — grava uma vez, propaga para as três superfícies.

Campo `dados_cadastrais` (+ `dados_cadastrais_atualizado_em`): dados cadastrais pessoais completos (documentos — CPF, RG, título de eleitor, PIS/PASEP, CTPS, CNH —, contato, família, formação acadêmica, carreira, dados bancários, plano de saúde etc.), ver `functions/dados_cadastrais.py`. Diferente de `ai_profile`, **não** é injetado na persona estática de nenhuma superfície — só é lido sob demanda pela ferramenta `consultar_dados_cadastrais` (`main.py`, gate condicional por palavras-chave amplo o bastante para cobrir todas as seções — documentos, contato, família, formação, carreira; `godmode.py`, sempre declarada), porque parte do dado é sensível o bastante para não valer a pena tê-lo em todo prompt. Leitura por seção (parâmetro `secao`, opcional): o objeto completo (~11k caracteres) estoura o teto de truncamento de resultado de ferramenta dos dois loops de tool-calling (8k no Godmode, 12k no copiloto) — sem `secao` a ferramenta só lista as seções disponíveis, com `secao` devolve o conteúdo completo daquela seção. Sem ferramenta de escrita para a IA: gravado/atualizado via `scripts/seed_dados_cadastrais.py`, rodado localmente a partir de um JSON fora do controle de versão — usa `merge` por field path (não `merge=True` recursivo) para que uma seção removida do payload realmente desapareça do Firestore, em vez de sobreviver como resíduo obsoleto.

### `resumo_matinal`
Resumo Matinal — a primeira tela do dia (`MorningSummaryView.tsx`, `viewMode 'home'`). ID do doc = `YYYY-MM-DD`, simétrico a `diario_pessoal`. Produzido **inteiramente em código**, sem nenhuma chamada de LLM, por `build_morning_summary` (`morning_summary.py`) — o frontend só desenha. Campos: `data`, `dia_semana`, `versao`, `gerado_em`, `foco[]` (até 3 ações escolhidas por regra explícita — `regra` é o id da regra que disparou: `prazo_final_iminente`, `degradacao_critica`, `sla_estourado`, `meta_parada`, `agendada`, `fila_avanco` — mais `motivo`, `proximo_passo`), `hoje` (`avanco`/`continuo`/`aguardando_terceiro`/`atrasadas`, cada ação com `herdada`, `degradation_count`, `proximo_passo` e progresso do `plano_acao`), `agenda[]`, `janelas_livres[]` (buracos ≥45min entre 07h e 19h), `prazos_duros[]` (`prazo_final` nos próximos 7 dias — o único prazo que o reset da meia-noite não move), `carga_semana[]`, `filas` (contagem + amostra das decisões **pendentes**: `sugestoes_vinculo`, `fusoes_contatos`, `notificacoes_ia`, `contas` — `whatsapp_consolidacoes` ficou deliberadamente de fora: consolidar uma conversa costuma ser um fim em si, e nem anexar a uma ação nem deixar como está são decisões pendentes), `saude` (rotinas de hoje com `verificavel`/`feito` — só pesagem, cintura e os dois check-ins deixam rastro conferível, o resto é aviso ilustrativo e vem com `feito: null`; mais `pesagem_registrada`, `cintura_registrada`, `checkin_manha`, `checkin_noite`, `peso`, `dor_ontem` e `ultimo_registro`), `estrategia` (`metas[]` com `gerida_por_acoes`, `paradas[]`, `servidas_hoje`, `total_geridas_por_acoes`), `ontem` (concluídas + texto do diário), `perfil` (leitura de `ai_profile.personalidade`), `contadores`, `visto_em` (gravado pela UI na primeira abertura do dia).

O pilar `saude` de `estrategia_pessoal` não é executado por ações (`gerida_por_acoes: false`): ele vive nos registros do módulo Saúde, então seu movimento vem de `saude.ultimo_registro` e ele fica fora do denominador de "metas que recebem trabalho hoje". Sem isso a tela afirmaria "parada há N dias" num dia em que houve pesagem. Segue em aberto um problema estrutural mais amplo do módulo Estratégia: `metricaAlvo.valorAtual` das metas absolutas nunca é sincronizado com a fonte real do dado (o peso vive em `health_weights`), então `progresso_pct` pode estar defasado.

O bloco `foco[]` fica persistido de propósito: é o que permite, numa camada futura, medir aderência (dos focos propostos, quantos saíram) sem reconstruir a manhã. Escrito por `gerar_resumo_matinal` (scheduler 04:30 BRT) e pela callable `gerarResumoMatinal`, ambas com `set(merge=True)` para preservar `visto_em`. Flag `system/settings.resumo_matinal.enabled` (padrão ligado).

### `diario_pessoal`
Diário pessoal diário, em primeira pessoa, gerado a partir das interações do usuário em todas as superfícies do Hermes (ver `personal_diary.py`). ID do doc = `YYYY-MM-DD`. Campos: `data`, `texto`, `texto_original` (se editado), `fontes` (contagens por origem: notas manuais, ações, saúde, financeiro, agenda, conversas, pessoas), `gerado_em`, `modelo`, `editado`, `editado_manualmente` (edição livre do texto na UI web), `confirmado`, `ajustes[]` (`{pedido, em}` — cada revisão pedida pelo usuário via Telegram ou pela UI web, insumo do consolidador de personalidade), `notas_manuais[]` (`{texto, em}` — anotações que o usuário deixa ao longo do dia na UI web para entrarem na consolidação das 21h30; o doc pode existir só com elas antes da geração), `sem_material` (dia sem atividade registrada). Escrito por `gerar_diario_pessoal` (scheduler 21:30 BRT, `set` com `merge=True` para preservar as notas manuais), `apply_diary_feedback` (ajuste via Telegram, callback `diary_edit:{data}`/`diary_ok:{data}` em `hermes_core_logic.py`), pela callable `ajustarDiarioPessoal` (ajuste via IA a partir da UI web) e diretamente pelo frontend (`PersonalDiaryView.tsx` — notas manuais e edição livre do texto). Lido também pelo Godmode (`consultar_diario_pessoal`) — é a fonte mais densa que ele tem do panorama recente do usuário, já que cada diário cruza ações/saúde/finanças/agenda/conversas/pessoas do dia. Flag `system/settings.personal_diary.enabled`.

### `correcoes_pendentes`
Fila de correções a aplicar em tarefas, detectadas por callables diversas; processada em lote por `processar_correcoes_pendentes` (scheduler, a cada 60 min).

### `long_transcriptions`
Transcrições de áudio longo via Google Speech-to-Text: `userId`, `createdAt`. Criado por `transcreverAudio` e pelo trigger de Storage `on_long_transcription_uploaded`. Índice: `userId+createdAt` (DESC).

### `quality_logs`
Logs de qualidade/feedback de respostas geradas pelo sistema.

## Pessoas, projetos e bolsistas

### `perfil_pessoas`
Contatos, bolsistas e colaboradores: `nome`, `email`, `telefone`, `whatsapp_chat_id` (ID de chat 1:1 `@c.us`), `cpf`/`rg`, `dados_bancarios`, `lattes`, `origem` (`manual`\|`google_contacts`\|`extracao_ia`), `google_contact_id`, `resumo_ia`. Escrito pelo frontend, por `sync_google_contacts`, `linkWhatsappContacts`, `generate_contact_summary`, e por extratores de menções em tarefas (`knowledge_graph.py`).

### `vinculos_projeto`
Vínculo de bolsista/colaborador a um projeto: `pessoa_id`, `projeto_id`, `tipo_bolsa_id`, `percentual_recebimento`, `funcao`, `status`, `documentos`, `valor_bolsa_mensal_atual`. Relações: → `perfil_pessoas`, → `projetos`, → `tipo_bolsas`.

### `projetos`
Projeto/departamento com orçamento (`orcamento`: custeio, capital, bolsas) e token de registro público (`public_registration_token`) usado pelos portais públicos de `security_portals.py`.

### `tipo_bolsas`
Catálogo de modalidades de bolsa: `nome_modalidade`, `valor_integral`, `valor_parcial`.

### `interacoes_pessoas`
Histórico de interações por pessoa: `pessoa_id`, `tipo` (`mencao_tarefa`\|`mencao_diario`\|`reuniao`\|`manual`\|`mencao_copiloto`\|`whatsapp`), `data`, `descricao`, `consolidacao_id` (se tipo `whatsapp`). Escrito por extratores de menções (`on_tarefa_written_extract_people`), pelo Copiloto e pela consolidação da Caixa de Entrada WhatsApp (`whatsapp_consolidation.py`).

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
Log diário (`id` = `YYYY-MM-DD`): exercícios (`pushups`, `pullups`, `plank`, `squats`, `walk`...), `calories`, `heartRate`, `sleep`, `pain`, `walkBlocks[]`. O campo `walkBlocks` guarda os blocos intermitentes de caminhada na esteira (`distance` em km obrigatório; `time`, `minutes`, `steps`, `calories` e `source` `web`|`telegram` opcionais), registrados pelo painel de saúde ou pelo comando "caminhada X" no Telegram — é a fonte da meta diária de distância. O campo `walk` é legado da antiga sincronização com o Google Health/Fit (removida) e não é mais gravado.

### `health_weights`
Histórico de peso por dia: `date`, `weight`, `fatPercentage`, `muscleMass`.

### `health_daily_habits` (descontinuada)
Checklist diário de hábitos, removido do sistema. A coleção permanece apenas como histórico e não é mais lida nem gravada pelo app.

### `health_telegram_reminders`
Reminders de saúde enviados via Telegram: `title`, `time`, `daysOfWeek[]`, `category` (`spine`\|`walking`\|`nutrition`\|`pain`\|`custom`), `last_sent_date`.

### `exames`
Exames e consultas médicas: `titulo`, `doutor_local`, `resultados`, `data`, `tipo` (`exame`\|`consulta`), `pool_dados[]`.

## Sistema, operacional e integrações

| Coleção | Representa | Escreve |
|---|---|---|
| `email_action_suggestions` | Motor **multi-canal** de sugestões de vínculo sinal↔ação (`tarefas`) em andamento/stand-by, confirmadas via Telegram ou pela fila web (`EmailLinkSuggestionsPanel` em `DashboardView.tsx`). Nome da coleção é histórico (nasceu só para e-mail). ID do doc = ID natural do sinal no canal (dedupe estrutural — mensagem Gmail, `sipac_{notificationId}`, `calendar_{google_event_id}`, ...). Campos comuns: `canal` (`email`\|`whatsapp`\|`sipac`\|`calendar`\|`pagina`), `titulo_sinal`, `origem_sinal`, `link_externo`, `analyzed_at`, `related`, `confidence` (0-1), `task_id`/`task_titulo`/`task_status` (se `related`), `resumo`, `nota_sugerida`, `reativar_sugerido`, `status` (`no_match`\|`pending`\|`applied`\|`applied_reactivated`\|`dismissed`\|`expired`), `telegram_sent`, `sent_at`, `applied_at`, `decided_at`. O produtor de e-mail (o único com matching por IA) também grava `google_message_id`, `subject`, `sender`, `snippet`, `internal_date`, `model`. O produtor de WhatsApp (`whatsapp_ingest.py`) grava campos executivos adicionais — `itens_de_acao[]` (`descricao`, `responsavel`, `prazo`), `decisoes[]` (pontos de decisão/auditoria), `datas_mencionadas[]`, `periodo_inicio`/`periodo_fim`, `n_mensagens` e, quando a conversa justifica, `mutacoes_propostas` (`novas_etapas[]` para `plano_acao`, `nova_data_limite`, `lembrete_sugerido`) — aplicadas em `tarefas` por `apply_suggestion(..., apply_mutations=True)` só mediante confirmação humana (botão "Registrar + aplicar mudanças"). | `email_action_linker.py` — `link_emails_to_actions` (e-mail, chamada no fim de `run_full_sync`), `queue_and_maybe_send_suggestion` (ponto de entrada genérico usado pelos demais produtores: `on_sipac_processo_updated`, `link_calendar_events_to_actions`, Monitor de Páginas, `whatsapp_ingest.py:triage_whatsapp_messages`); status decidido pelo callback `emlink:{id}:{ok\|on\|mut\|no}` em `hermes_core_logic.py` (`mut` aplica as mutações propostas) |
| `atencao` | Fila unificada de atenção: itens e pendências que demandam decisão ou acompanhamento do dono (`origem`, `tipo`, `prioridade`, `titulo`, `resumo`, `acao_id`, `etapa_id`, `pessoa`, `prazo`, `evidencia`, `sugestao`, `estado`, `chave_dedupe`, `criado_em`, `atualizado_em`, `resolvido_em`, `desfecho`). ID do doc = `chave_dedupe` determinística. Índice composto: `estado ASC, prioridade ASC, prazo ASC`. | `functions/atencao.py` (`detectar_atencao_acoes`, scheduler a cada 30 min); resolvida via MCP tool `resolver_item_atencao`; lida por `obter_fila_atencao` e `obter_estado_atual` |
| `agent_requests` | Fila de trabalho autônomo (nível "Autônomo", sem efeito em terceiros) consumida por sessões agendadas do Claude (`tipo`, `status`: `pendente`\|`em_andamento`\|`concluido`\|`erro`, `payload`, `origem`, `item_atencao_id`, `acao_id`, `criado_em`, `atualizado_em`, `processado_em`, `resultado`, `erro`). ID do doc determinístico (`consolidar_audio:{item_atencao_id}`). | `functions/atencao_whatsapp.py` (hook no detector `audio_relevante`); lida via MCP tool `consultar_pedidos_agente` e concluída via `concluir_pedido_agente` |
| `agent_runs` | Registro de observabilidade das execuções de rotinas agendadas do Claude (`rotina`, `resumo`, `status`: `sucesso`\|`erro`\|`parcial`, `contadores`, `erro`, `iniciado_em`, `finalizado_em`, `criado_em`). ID do doc gerado automaticamente. | gravado via MCP tool `registrar_execucao_agente` e consultado via `consultar_execucoes_agente` |
| `promessas_abertas` | Compromissos de resposta que o dono fez por WhatsApp (`chat_id`, `chat_name`, `mensagem_id`, `texto`, `prometido_em`, `vence_em`, `estado`: `aberta`\|`cumprida`\|`vencida`, `acao_id`). ID do doc = `{chat_id}_{mensagem_id}`. So uma promessa `aberta`/`vencida` por chat - uma nova promessa substitui a anterior. Indice composto: `estado ASC, vence_em ASC`. | `functions/atencao_whatsapp.py` (`on_whatsapp_message_atencao`, trigger on-create em `whatsapp_messages`; `vencer_promessas`, scheduler a cada 15 min) |
| `notificacoes` | Notificações do app, espelhadas no Telegram | `emit_notification_backend`, trigger `on_notificacao_created` |
| `system_reminders` | Cache para evitar duplicar reminders já enviados | `check_and_send_reminders` |
| `scheduled_notifications` | Fila de notificações agendadas pelo planejador proativo de IA (`title`, `message`, `category`, `send_at`, `status`: `pending`\|`sent`\|`failed`, `source: "ai_planner"`, `motivo`, `feedback`: `null`\|`useful`\|`dismissed`) — enviadas ao Telegram com botões de feedback, não passam pela coleção `notificacoes` | `ai_notification_planner.py` (`propor_notificacao`, `ai_notification_planner_daily`); consumida e marcada por `dispatch_pending_ai_notifications` (chamada de dentro de `check_and_send_reminders`); `feedback` atualizado pelo callback `ai_notif:{id}:{useful\|dismiss}` em `hermes_core_logic.py` |
| `relatorios` | Relatórios gerados (PGD e resumos) | `salvarRelatorioNoDrive`, callables de resumo |
| `google_calendar_events` | Eventos do Google Calendar sincronizados | `sync_google_calendar`, `run_full_sync` |
| `sipac_processos` | Processos SIPAC sincronizados (scraper externo via PubSub) | trigger `on_processo_updated` |
| `whatsapp_outbox` | Fila de mensagens WhatsApp agendadas e rascunhos com aprovação via Telegram ou WhatsApp próprio (`to_number`, `content`, `status`: `pending`\|`sending`\|`sent`\|`failed`\|`aguardando_aprovacao`\|`descartado`\|`expirado`, `motivo`, `acao_id`, `item_atencao_id`, `origem`, `destinatario_nome`, `telegram_message_id`, `aprovado_via`: `"telegram"`\|`"whatsapp"`, `scheduled_for`, `created_at`, `aprovado_em`, `descartado_em`, `expirado_em`). Coordenação de quem envia (worker local vs. card Telegram) via `system/settings.whatsapp_auto_send_enabled` + heartbeat | `schedule_whatsapp_message` e `criar_rascunho_whatsapp` (`tools`); callbacks Telegram `outbox:{id}:{ok\|edit\|no}`; resposta `from_me` no self-chat (`whatsapp_owner_chat_id`); consumida por `services/whatsapp-capture` (cron) ou `dispatch_scheduled_whatsapp_messages` |
| `whatsapp_chats` | Registro de todos os chats da conta WhatsApp (`chat_id`, `chat_name`, `is_group`, `last_activity_ts`, `last_synced_at`) — populado a cada 6h e 60s pós-ready pelo worker local; base para nomes de chat e matching com contatos | microsserviço `services/whatsapp-capture`; lido por `listWhatsappChats` e `linkWhatsappContacts` |
| `whatsapp_messages` | Mensagens capturadas pelo microsserviço WhatsApp, só das conversas em `system/settings.whatsapp_ingest.chats_allowlist` — ver [Integração WhatsApp](/docs/okf/integracoes/whatsapp.md). `transcription_text`/`transcription_model` são cache de transcrição do job de consolidação; `consolidation_ids[]` marca mensagens já consolidadas. Índice composto `chat_id`+`timestamp` (timeline da Caixa de Entrada) | microsserviço `services/whatsapp-capture`; `whatsapp_consolidation.py` (cache/marcação); lida por `WhatsappInboxView.tsx` |
| `whatsapp_consolidacoes` | Jobs de consolidação da Caixa de Entrada WhatsApp — requisição (`chat_id`, `message_ids[]` máx. 200), ciclo de vida (`status` queued→processing→completed/error, `progress`), resultado (`transcript_literal` montado por código, `resumo`, `itens_de_acao[]`, `decisoes[]`, `periodo_*`, contadores, `attachments[]`, `digest_id`) e associação (`task_id`, `task_titulo`, `applied_at`). Índice composto `chat_id`+`requested_at` | `WhatsappInboxView.tsx` (addDoc = RPC, padrão `copilot_jobs`); trigger `on_whatsapp_consolidacao_created` |
| `whatsapp_digests` | Digests vetorizados de conversas do WhatsApp (nunca mensagem a mensagem) — `chat_id`, `chat_name`, `resumo`, `topicos[]`, `relevancia`, `itens_de_acao[]`, `decisoes[]`, `datas_mencionadas[]`, `embedding` (Vector 768). Produtor atual: job de consolidação (IDs `consol_*`, relevancia `consolidacao`); a triagem automática (IDs `{chat_id}_{ts}`) está dormente | `whatsapp_consolidation.py`; `whatsapp_ingest.py:triage_whatsapp_messages` (legado); lida por `whatsapp_ingest.py:buscar_conversas_whatsapp` (tool do copiloto e do Godmode) |
| `system/whatsapp_ingest` | Cursor de processamento (`last_processed_at`) da triagem de WhatsApp | `whatsapp_ingest.py:triage_whatsapp_messages` |
| `system/whatsapp_worker` | Heartbeat do worker local (`last_seen`, `ready`) — usado por `dispatch_scheduled_whatsapp_messages` para decidir se deixa o worker enviar de verdade | `services/whatsapp-capture` (a cada 5 min) |
| `system/api_keys`, `system/settings`, `system/config`, `system/sync`, `system/google_credentials`, `system/file_search`, `system/cost_controls` | Documentos de configuração e estado global, na coleção `system`. `system/settings` inclui: flags de detectores de atenção (`atencao.promessa_sem_retorno`, `atencao.audio_relevante`), `whatsapp_auto_send_enabled`, `whatsapp_owner_chat_id` (chat_id `@c.us` do próprio dono para aprovação/descarte/edição de rascunhos no WhatsApp), etc. | admin/setup scripts; `on_sync_request`; `start_file_indexing` |
| `system_usage/gemini/daily/{data}` | Telemetria diária de uso/custo da API Gemini | `log_gemini_usage` (`gemini_cost_controls.py`) |
| `system_usage/ai_planner_notifications/daily/{data}` | Contador atômico (`count`) do teto diário de `scheduled_notifications` propostas pelo planejador de IA — lido e incrementado dentro da mesma transação Firestore que cria a notificação, para não estourar o teto sob tool calls concorrentes (`ThreadPoolExecutor`) ou execuções sobrepostas do scheduler | `_reserve_and_create_notification` (`ai_notification_planner.py`) |
| `idempotency` | Deduplicação de requisições (TTL via `expires_at`) | `core/idempotency.py` |
| `telegram_sessions` | Sessões ativas de Telegram (TTL via `expires_at`) | `core/session.py` |
| `whitelist` | Chat IDs de Telegram autorizados | admin (`hermes_core_logic.py`) |
| `paginas_monitoradas` | Monitor de Páginas: `url`, `apelido`, `objetivo`, `seletor_css`, `hash_atual`, `texto_atual`, `ultima_verificacao`/`ultima_mudanca`/`ultima_analise`, `ativo`, `userId`, `task_id` (opcional — se preenchido, avanço do objetivo propõe registrar no diário da ação via `queue_and_maybe_send_suggestion` em vez de alerta avulso no Telegram) | frontend (`MonitorPaginasTool.tsx`); `scheduled_page_monitor` (`main.py`) |
| `configuracoes`, `public_configs`, `unidades` | Configurações de app e unidades organizacionais | frontend / admin |

## Convenções gerais

- Datas são strings ISO 8601, exceto `createdAt` em algumas coleções de jobs que usa `Timestamp` nativo do Firestore.
- Embeddings usam o tipo `Vector` nativo do Firestore (768 dimensões, `gemini-embedding-001`) — gravar como lista simples deixa o documento invisível ao `find_nearest`.
- IDs de documento costumam ser auto-gerados, exceto séries diárias (`health_*`, `system_usage/gemini/daily/*`), que usam `YYYY-MM-DD` como ID.
