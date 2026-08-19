---
type: reference
title: Mapa de Cloud Functions
description: Cloud Functions exportadas pelo backend Python do Hermes, agrupadas por arquivo e tipo de trigger.
resource: functions/main.py
tags: [hermes, okf, cloud-functions, firebase, arquitetura]
timestamp: 2026-08-14T00:00:00-03:00
---

# Mapa de Cloud Functions

O backend roda em Cloud Functions Python (gen2). Há ~80 funções exportadas em `functions/`. Tipos de trigger usados: HTTPS Callable (chamada autenticada do frontend via `httpsCallable`), Firestore trigger (on-create/on-update/on-write), Scheduler (cron), PubSub (workers assíncronos), Storage (on-finalize) e HTTP request puro (webhooks).

## `functions/main.py` (~52 funções)

### Sincronização e dados
| Função | Trigger | O que faz |
|---|---|---|
| `sync_gmail_bills_callable` | Callable | Sincroniza boletos/Pix a partir do Gmail |
| `on_sync_request` | Firestore update (`system/sync`) | Dispara sincronização completa (Tasks, Calendar, e-mails) |
| `scheduled_sync` | Scheduler (30 min) | Sincronização periódica automática |
| `on_tarefa_written` | Firestore write (`tarefas/{id}`) | Monitora mudanças de horário/prazo |
| `on_processo_updated` | Firestore update (`tarefas/{id}`) | Detecta `processo_sei` e aciona scraper SIPAC via PubSub |
| `link_emails_to_actions` (`email_action_linker.py`) | (interno, chamado por `run_full_sync` após `sync_boletos_gmail`) | Analisa e-mails recentes via IA, propõe vínculo com ações em andamento/stand-by por Telegram (`emlink:{msgId}:{ok\|on\|mut\|no}`) e grava em `email_action_suggestions`; sempre exige confirmação humana (nunca aplica sozinho — a classificação vem de conteúdo controlado pelo remetente do e-mail). Flag `system/settings.email_action_linker.enabled` |
| `link_calendar_events_to_actions` (`email_action_linker.py`) | (interno, chamado por `run_full_sync` após `link_emails_to_actions`) | Propõe registrar no diário o fechamento de reuniões vinculadas a uma ação (`tarefas.google_calendar_id`) — matching determinístico, sem IA. Mesma flag `email_action_linker.enabled` |
| `try_link_sipac_notification` (`email_action_linker.py`) | (interno, chamado por `on_notificacao_created` quando `link == '@SipacTrackingTool'`) | Casa `notificacoes.numeroProcesso` (gravado pelo scraper Node) com `tarefas.processo_sei` — matching determinístico, sem IA. Se enviar o cartão de confirmação, o espelhamento genérico da notificação no Telegram é pulado |
| `triage_whatsapp_messages` (`whatsapp_ingest.py`) | (interno, chamado por `run_full_sync` após `link_calendar_events_to_actions`) | **Legado, dormente desde 2026-08-14** (flag `system/settings.whatsapp_ingest.enabled = false`) — substituída pela consolidação manual da Caixa de Entrada (`on_whatsapp_consolidacao_created`). Quando ligada: agrupa mensagens novas de `whatsapp_messages` por conversa, classifica cada janela via IA (`acao`\|`conhecimento`\|`ruido`), propõe o vínculo (canal `whatsapp`, `emlink:{id}:{ok\|on\|mut\|no}`) e grava digest vetorizado em `whatsapp_digests`; conversas vinculadas manualmente (`tarefas.whatsapp_vinculos`) restringem as candidatas do prompt |
| `getAutomationSettings` / `updateAutomationSettings` | Callable | Única porta de entrada do frontend para o subconjunto de `system/settings` das automações multi-canal (`email_action_linker`, `personal_diary`, `whatsapp_ingest`, `whatsapp_auto_send_enabled`) — o documento `system/*` é bloqueado por regra de segurança para o cliente. UI: aba "Automações" em `SettingsModal` (`src/components/modals/Modals.tsx`) |
| `listWhatsappChats` | Callable | Lista chats de WhatsApp conhecidos/registrados (união de `system/settings.whatsapp_ingest.chats_allowlist`, mensagens recentes em `whatsapp_messages` e o registro `whatsapp_chats` persistido pelo worker local) — usado pelo seletor de vínculo manual em `TaskExecutionView.tsx` e pela Caixa de Entrada (`WhatsappInboxView.tsx`). Suporta `include_all: bool` para listar todo o registro marcando `monitored: false` nos não capturados |
| `on_whatsapp_consolidacao_created` | Firestore create (`whatsapp_consolidacoes/{jobId}`) | Job de consolidação da Caixa de Entrada WhatsApp (GB_1, 540s; núcleo em `whatsapp_consolidation.py`): transcreve áudios da seleção (Groq/Whisper com fallback Gemini, cacheando em `whatsapp_messages.transcription_text`), monta transcript literal por código, sintetiza resumo/itens de ação/decisões (1 chamada Gemini restrita ao transcript), grava digest curado `consol_*` em `whatsapp_digests` e marca as mensagens (`consolidation_ids`). Progresso/resultado empurrados por campos no próprio doc do job (padrão `copilot_jobs`) |
| `on_vectorize_requested` | PubSub (`vectorize-process`) | Processa vetorização de documentos |
| `vectorize_process_docs_callable` | Callable | Vetoriza documentos de uma tarefa |
| `upload_to_drive` | Callable | Upload de arquivo para o Google Drive |

### Notificações e reminders
| Função | Trigger | O que faz |
|---|---|---|
| `on_notificacao_created` | Firestore create (`notificacoes/{id}`) | Espelha notificação para o Telegram |
| `check_and_send_reminders` | Scheduler (1 min) | Dispara reminders de tarefas/saúde/financeiro; também despacha (`dispatch_pending_ai_notifications`) a fila `scheduled_notifications` gerada pelo planejador de IA |

### Conhecimento e RAG
| Função | Trigger | O que faz |
|---|---|---|
| `vectorizeKnowledgeItemCallable` | Callable | Vetoriza item de `conhecimento` |
| `extractAndVectorizeRAGItem` | Callable | Extrai texto e vetoriza item RAG |
| `on_knowledge_item_updated` | Firestore update (`conhecimento/{id}`) | Reage a atualização de item de conhecimento |
| `findSimilarKnowledge` | Callable | Busca itens similares por embedding |
| `on_arquivo_adicionado` | Firestore create (`conhecimento/{id}`) | Reage à criação de novo arquivo |

### Tarefas e ações
| Função | Trigger | O que faz |
|---|---|---|
| `generate_task_with_ia` | Callable | Gera tarefa via IA a partir de contexto |
| `processExtraContextFile` | Callable | Processa arquivo de contexto extra para RAG |
| `criarLembreteNoGoogleTasks` / `removerLembreteDoGoogleTasks` | Callable | Cria/remove reminder no Google Tasks |
| `confirmarEdicaoAcao` | Callable | Confirma edição de ação após validação |
| `confirmarReagendamentoEmLote` | Callable | Reagenda múltiplas ações em lote |

### Áudio e transcrição
| Função | Trigger | O que faz |
|---|---|---|
| `transcreverAudio` / `transcrever_audio` | Callable | Transcreve áudio via Google Speech-to-Text |
| `on_long_transcription_uploaded` | Storage finalize | Processa transcrição longa enviada ao Storage |

### Apresentações e conteúdo
| Função | Trigger | O que faz |
|---|---|---|
| `processarArquivoIA` | Callable | Analisa/extrai conteúdo de arquivo com IA |
| `criar_formulario_google` | Callable | Cria Google Form vinculado a uma tarefa |
| `corrigir_sintaxe_mermaid` | Callable | Corrige sintaxe de diagramas Mermaid |
| `processInvoiceOCR` | Callable | OCR de faturas via Gemini Vision |

### Copiloto e chat
| Função | Trigger | O que faz |
|---|---|---|
| `askTaskAssistant` | Callable | Assistente com contexto de uma tarefa específica |
| `askChatbot` | Callable | Chatbot genérico sem contexto específico |
| `askCopilotoHermes` | Callable | Copiloto principal — memória, RAG, tool calling. Exige dono verificado (`_require_internal_user`), não só `req.auth` — roda com Admin SDK, que ignora `firestore.rules` |
| `confirmarConflitoMemoria` | Callable | Resolve conflito detectado em memória do Copiloto |

### Análises e insights
| Função | Trigger | O que faz |
|---|---|---|
| `analisarPadroesCategoriaIA` | Callable | Analisa padrões de categorização |
| `sintetizarDescricaoAcao` | Callable | Sintetiza descrição automática de uma ação |
| `analisarInsightProativo` | Callable | Gera recomendações proativas |
| `processar_correcoes_pendentes` | Scheduler (60 min) | Aplica em lote correções enfileiradas |

### Relatórios
| Função | Trigger | O que faz |
|---|---|---|
| `salvarRelatorioNoDrive` | Callable | Salva relatório gerado no Google Drive |
| `salvarTranscricaoReuniao` | Callable | Salva transcrição de reunião |

### Financeiro, saúde e contatos
| Função | Trigger | O que faz |
|---|---|---|
| `gerarResumoFinanceiro` | Callable | Resumo financeiro gerado por IA |
| `gerarResumoSaude` | Callable | Resumo de saúde/bem-estar gerado por IA |
| `classificarAreaTematica` | Callable | Classifica `area_tematica` de uma tarefa |
| `sync_google_contacts` | Callable | Sincroniza com Google Contacts |
| `generate_contact_summary` | Callable | Resumo IA de um contato |
| `merge_contacts` | Callable | Mescla contatos duplicados |
| `linkWhatsappContacts` | Callable | Vincula contatos de `perfil_pessoas` a chats individuais (@c.us) do WhatsApp cruzando os últimos 8 dígitos do telefone (matching determinístico 1-para-1 estrito com relatório) |

### Logging e custos
| Função | Trigger | O que faz |
|---|---|---|
| `relatorio_diario_custo_gemini` | Scheduler (20h30 BRT) | Resumo diário de custo Gemini no Telegram |
| `consolidar_memorias_copiloto` | Scheduler (4h BRT) | Consolida memórias do Copiloto |
| `gerar_diario_pessoal` (`personal_diary.py`) | Scheduler (21h30 BRT) | Agrega ações, saúde, finanças, agenda, conversas (`sessoes_copiloto` e `sessoes_godmode`) e pessoas do dia (`tarefas`, `health_*`, `finance_transactions`, `google_calendar_events`, `interacoes_pessoas`) e usa um modelo de linguagem para redigir o diário pessoal do dia em primeira pessoa, salvo em `diario_pessoal/{data}`; entrega no Telegram com botões "✍️ Ajustar"/"👍 Ok". Flag `system/settings.personal_diary.enabled` |
| `consolidar_personalidade` (`personal_diary.py`) | Scheduler (domingo 22h BRT) | Destila os diários da semana (+ ajustes pedidos pelo usuário) num perfil de personalidade em `usuarios/{uid}.ai_profile.personalidade`, versionado. Mesma flag `personal_diary.enabled` |

## `functions/knowledge_graph.py` (~9 funções)

| Função | Trigger | O que faz |
|---|---|---|
| `on_tarefa_created_kg` | Firestore create (`tarefas/{id}`) | Fase 1 do grafo: gera `kg_tags` (Retrieval-First) |
| `on_tarefa_concluida_kg` | Firestore update (`tarefas/{id}`) | Fase 2: cristaliza tarefa concluída em nó conceitual (Dual-Pass) |
| `on_tarefa_written_extract_people` | Firestore write (`tarefas/{id}`) | Extrai menções de pessoas na tarefa |
| `buscar_procedimento` | Callable | Busca nós do grafo por query livre (tool do Copiloto) |
| `crystallize_task_manual` | Callable | Cristaliza manualmente uma tarefa (uso administrativo/migração) |
| `processar_artefato_kg` | PubSub (`hermes-artefato-kg`) | Vetoriza e indexa artefato de tarefa |
| `monitorar_acervo_global` | Scheduler | Varre a Pasta de Deságue e indexa novos arquivos |
| `extract_kg_rag_context` | Callable | Extrai subgrafo RAG com decaimento temporal |
| `smart_search_kg` | Callable | Busca híbrida (lexical + semântica) no grafo |
| `get_artefato_raw_text` | Callable | Retorna texto bruto de um artefato indexado |

## `functions/hermes_core_logic.py`

| Função | Trigger | O que faz |
|---|---|---|
| `telegramWebhook` | HTTP request | Recebe updates do bot do Telegram |
| `on_telegram_inbound` | Firestore create (`telegram_inbound/{id}`) | Processa mensagem recebida do Telegram |
| `_handle_telegram_callback` | (interno, chamado por `telegramWebhook`) | Processa botões inline, inclusive `ai_notif:{id}:{useful\|dismiss}` (grava feedback em `scheduled_notifications`), `emlink:{id}:{ok\|on\|mut\|no}` (aplica/ignora sugestão de vínculo sinal↔ação em `email_action_suggestions`; `mut` também aplica as `mutacoes_propostas` na tarefa vinculada) e `diary_edit:{data}`/`diary_ok:{data}` (trava a sessão para capturar um ajuste ao diário pessoal do dia, ou confirma sem alteração) |

## `functions/godmode.py`

Modo estratégico do Copiloto sobre Claude (Anthropic) em vez de Gemini — módulo aditivo, não altera o fluxo de `askCopilotoHermes`. Sessões em `sessoes_godmode` (+ subcoleção `mensagens`), mesmo formato de `sessoes_copiloto`.

| Função | Trigger | O que faz |
|---|---|---|
| `askHermesGodmode` | Callable | Loop de tool-calling com Claude (`llm_providers/claude_provider.py`). Ferramentas de leitura ampla — tarefas (`consultar_tarefas`), metas estratégicas (`consultar_metas_estrategicas`), finanças (`consultar_financas`, via `tools/telegram_extended.py`), saúde (`consultar_saude`/`consultar_relatorio_semanal_saude`, via `health_tools.py`), diário pessoal (`consultar_diario_pessoal`), agenda (`consultar_agenda`), pessoas (`buscar_contato`/`consultar_interacoes_pessoa`), WhatsApp (`buscar_conversas_whatsapp`), dados cadastrais pessoais (`consultar_dados_cadastrais`, via `dados_cadastrais.py` — CPF/RG/bancários/plano de saúde etc., só lidos sob demanda, nunca injetados na persona) e conhecimento/RAG (`buscar_conhecimento`) — e escrita restrita ao módulo Estratégia (`criar_objetivo_estrategico`, `editar_objetivo_estrategico`, `gerenciar_item_estrategico`, `excluir_objetivo_estrategico`, via `strategy_tools.py`, compartilhado com `main.py`) |

## `functions/ai_notification_planner.py`

Planejador proativo de notificações por IA — módulo aditivo, usa o mesmo provider/loop de tool-calling do Godmode (Claude), mas roda sem interação do usuário.

| Função | Trigger | O que faz |
|---|---|---|
| `ai_notification_planner_daily` | Scheduler (6h30 BRT, diário) | Agente com Claude analisa tarefas ativas e metas estratégicas (`estrategia_pessoal`) e propõe, via ferramenta `propor_notificacao`, no máximo `AI_PLANNER_MAX_DAILY_NOTIFICATIONS` (padrão 3) notificações para o dia, gravadas em `scheduled_notifications` (status `pending`) |
| `dispatch_pending_ai_notifications` | (interno, chamado por `check_and_send_reminders`) | Envia ao Telegram as notificações agendadas cujo `send_at` já chegou, com botões inline de feedback (👍 útil / 👎 dispensar), e marca `status: sent`/`failed` |

Financeiro e saúde ainda estão fora do escopo deste planejador — ele não foi migrado para os módulos `health_tools.py`/`tools/telegram_extended.py` recém-compartilhados com o Godmode (ver `functions/godmode.py` acima).

## `functions/security_portals.py`

Portais públicos (sem autenticação Firebase) acessados por links externos — ver tokens de registro em `projetos.public_registration_token`.

| Função | O que faz |
|---|---|
| `matchShoppingItemsAI` | Matching de itens de lista de compras via IA |
| `generatePgdFromDiariesAI` / `generatePgdFromRawTextAI` | Gera Plano de Trabalho a partir de diários/texto bruto |
| `getPublicFinancePortal` / `submitPublicFinanceTransaction` | Portal público de finanças (leitura/escrita) |
| `getPublicShoppingPortal` / `mutatePublicShoppingPortal` / `mutateShoppingList` | Portal público de lista de compras |
| `getPublicScholarshipProject` / `submitPublicScholarshipRegistration` | Portal público de registro de bolsista |

## `functions/daily_reset_job.py`

| Função | Trigger | O que faz |
|---|---|---|
| `daily_wip_reset_and_degradation` | Scheduler | Reset diário de status WIP e contagem de degradação |

## Padrões de integração

- **Callable (síncrono):** frontend chama via `httpsCallable()`; timeout máximo observado de 540s. Usado para a maioria das ações do usuário (Copiloto, geração de conteúdo, sincronizações sob demanda).
- **Firestore trigger (assíncrono):** uma escrita dispara processamento em cascata — principal mecanismo de propagação para o grafo de conhecimento (`on_tarefa_concluida_kg`).
- **PubSub (enfileirado):** usado para processamento pesado desacoplado da resposta ao usuário (vetorização, artefatos do grafo).
- **Scheduler (cron):** sincronizações periódicas, reminders, relatórios de custo, limpeza/reset diário.
- **HTTP request puro:** apenas o webhook do Telegram.

Integrações externas usadas por essas funções: Google Tasks, Google Calendar, Google Drive, Google Contacts, Google Speech-to-Text, Google Forms, Gemini (embedding + modelos de geração + File Search) e Telegram Bot API.
