---
type: reference
title: Mapa de Cloud Functions
description: Cloud Functions exportadas pelo backend Python do Hermes, agrupadas por arquivo e tipo de trigger.
resource: functions/main.py
tags: [hermes, okf, cloud-functions, firebase, arquitetura]
timestamp: 2026-06-17T00:00:00Z
---

# Mapa de Cloud Functions

O backend roda em Cloud Functions Python (gen2). Há ~78 funções exportadas em `functions/`. Tipos de trigger usados: HTTPS Callable (chamada autenticada do frontend via `httpsCallable`), Firestore trigger (on-create/on-update/on-write), Scheduler (cron), PubSub (workers assíncronos), Storage (on-finalize) e HTTP request puro (webhooks).

## `functions/main.py` (~51 funções)

### Sincronização e dados
| Função | Trigger | O que faz |
|---|---|---|
| `sync_gmail_bills_callable` | Callable | Sincroniza boletos/Pix a partir do Gmail |
| `on_sync_request` | Firestore update (`system/sync`) | Dispara sincronização completa (Tasks, Calendar, e-mails) |
| `scheduled_sync` | Scheduler (30 min) | Sincronização periódica automática |
| `on_tarefa_written` | Firestore write (`tarefas/{id}`) | Monitora mudanças de horário/prazo |
| `on_processo_updated` | Firestore update (`tarefas/{id}`) | Detecta `processo_sei` e aciona scraper SIPAC via PubSub |
| `on_vectorize_requested` | PubSub (`vectorize-process`) | Processa vetorização de documentos |
| `vectorize_process_docs_callable` | Callable | Vetoriza documentos de uma tarefa |
| `upload_to_drive` | Callable | Upload de arquivo para o Google Drive |

### Notificações e reminders
| Função | Trigger | O que faz |
|---|---|---|
| `on_notificacao_created` | Firestore create (`notificacoes/{id}`) | Espelha notificação para o Telegram |
| `check_and_send_reminders` | Scheduler (1 min) | Dispara reminders de tarefas/saúde/financeiro |

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
| `gerarSlidesIA` / `criar_apresentacao_slides` | Callable | Gera apresentação de slides via IA |
| `criar_formulario_google` | Callable | Cria Google Form vinculado a uma tarefa |
| `corrigir_sintaxe_mermaid` | Callable | Corrige sintaxe de diagramas Mermaid |
| `processInvoiceOCR` | Callable | OCR de faturas via Gemini Vision |

### Copiloto e chat
| Função | Trigger | O que faz |
|---|---|---|
| `askTaskAssistant` | Callable | Assistente com contexto de uma tarefa específica |
| `askChatbot` | Callable | Chatbot genérico sem contexto específico |
| `askCopilotoHermes` | Callable | Copiloto principal — memória, RAG, tool calling |
| `confirmarConflitoMemoria` | Callable | Resolve conflito detectado em memória do Copiloto |

### Análises e insights
| Função | Trigger | O que faz |
|---|---|---|
| `analisarPadroesCategoriaIA` | Callable | Analisa padrões de categorização |
| `sintetizarDescricaoAcao` | Callable | Sintetiza descrição automática de uma ação |
| `analisarInsightProativo` | Callable | Gera recomendações proativas |
| `processar_correcoes_pendentes` | Scheduler (60 min) | Aplica em lote correções enfileiradas |

### Pesquisa profunda
| Função | Trigger | O que faz |
|---|---|---|
| `startDeepResearch` / `cancelDeepResearch` | Callable | Inicia/cancela pesquisa profunda multi-turno |
| `deep_research_worker` | Firestore create (`deep_research_tasks/{id}`) | Worker que processa a pesquisa |

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

### Logging e custos
| Função | Trigger | O que faz |
|---|---|---|
| `relatorio_diario_custo_gemini` | Scheduler (20h30 BRT) | Resumo diário de custo Gemini no Telegram |
| `consolidar_memorias_copiloto` | Scheduler (4h BRT) | Consolida memórias do Copiloto |

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

## `functions/slides_orchestrator.py`

Pipeline assíncrono de geração de apresentações: strategist → executor → finalize.

| Função | Trigger | O que faz |
|---|---|---|
| `iniciarJobSlides` | Callable | Inicia job de geração de slides |
| `slideStrategistWorker` | PubSub (`slide-strategist`) | Define estratégia/outline da apresentação |
| `slideExecutorWorker` | PubSub (`slide-executor`) | Gera SVG/PPTX dos slides |
| `slideFinalizeWorker` | PubSub (`slide-finalize`) | Finaliza e salva a apresentação |
| `cancelSlideJob` | Callable | Cancela job em progresso |

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
- **PubSub (enfileirado):** usado para pipelines com múltiplos estágios (slides) ou processamento pesado desacoplado da resposta ao usuário (vetorização, artefatos do grafo).
- **Scheduler (cron):** sincronizações periódicas, reminders, relatórios de custo, limpeza/reset diário.
- **HTTP request puro:** apenas o webhook do Telegram.

Integrações externas usadas por essas funções: Google Tasks, Google Calendar, Google Drive, Google Contacts, Google Speech-to-Text, Google Forms, Gemini (embedding + modelos de geração + File Search) e Telegram Bot API.
