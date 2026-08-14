---
type: integration
title: Integração WhatsApp no Hermes
description: Microsserviço de captura de mensagens WhatsApp, triagem por IA com vínculo a ações e busca semântica via digests vetorizados.
resource: services/whatsapp-capture
tags: [hermes, whatsapp, integracao, gemini, firestore]
timestamp: 2026-08-14T00:00:00-03:00
---

# Integração WhatsApp no Hermes

> **Fluxo principal (desde 2026-08-14):** captura (worker local, §1-2) → **Caixa de Entrada WhatsApp** (`WhatsappInboxView.tsx`, §3) → consolidação manual (transcrição + síntese, `whatsapp_consolidation.py`) → diário da ação + digest curado (§4). A triagem automática por IA (§3-legado) foi substituída pela consolidação manual e fica dormente atrás do flag `whatsapp_ingest.enabled` (desligado).

## 1. Microsserviço de captura

- Local: `services/whatsapp-capture`
- Stack: `whatsapp-web.js` (não é a API oficial do WhatsApp Business — automação não-oficial via WhatsApp Web, sujeita a bloqueios/quebras) + `firebase-admin` + `node-cron`.
- **Roda na máquina local do usuário**, não em Cloud Functions — `whatsapp-web.js` controla um Chromium headless via `LocalAuth` (sessão persistida em `.wwebjs_auth/`, gitignored). Requer Node ≥18 (usa `fetch` global).
- Execução:
  ```bash
  cd services/whatsapp-capture
  npm install
  npm run start
  ```
  Primeira execução exibe um QR code no terminal para parear com o WhatsApp do celular. Requer `GOOGLE_APPLICATION_CREDENTIALS` no ambiente (mesmas credenciais de serviço do backend) e, opcionalmente, `FIREBASE_STORAGE_BUCKET` para o upload de mídia funcionar.

### Allowlist — nada é capturado por padrão

Por privacidade, o worker **não captura nenhuma conversa até ser configurado explicitamente**: só processa chats presentes em `system/settings.whatsapp_ingest.chats_allowlist` (array de IDs de chat do WhatsApp, ex.: `"5527999999999@c.us"` para contato, `"...@g.us"` para grupo). A lista é observada em tempo real (`onSnapshot`) — não precisa reiniciar o worker para adicionar/remover um chat.

### Resiliência

- `disconnected`/`auth_failure` disparam um alerta no Telegram (mesmo bot/chat do resto do Hermes) e o worker tenta reconectar automaticamente, exceto em `LOGOUT` (aí é preciso reescanear o QR).
- Heartbeat a cada 5 min em `system/whatsapp_worker.last_seen` — usado pela Cloud Function de despacho de WhatsApp (§4) para saber se o worker está de pé.

## 2. Armazenamento no Firebase

- Coleção Firestore: `whatsapp_messages`
- ID do doc: `{chat_id}_{wa_message_id}` — idempotente (sobrescreve em vez de duplicar numa redelivery/reconexão).
- Campos: `chat_id`, `chat_name`, `is_group`, `author_name`, `from_me`, `wa_message_id`, `timestamp` (quando a mensagem foi enviada no WhatsApp), `ingested_at` (quando o worker gravou — usado como cursor de processamento), `message_type`, `content`, `links[]`, `media` (`mimeType`, `sizeBytes`, `storage_path` se o upload ao Storage funcionou), `transcription_text`/`transcription_model` (preenchidos pelo job de consolidação como cache — reconsolidar nunca repaga transcrição), `consolidation_ids[]` (jobs de consolidação que incluíram a mensagem — badge "consolidada" na Caixa de Entrada).
- Índice composto: `chat_id` (ASC) + `timestamp` (DESC) — timeline da Caixa de Entrada.
- Captura tanto mensagens recebidas quanto enviadas (`from_me`), via um único listener em `message_create`.

## 3. Caixa de Entrada e consolidação manual

- View: `WhatsappInboxView.tsx` (raiz do repo), registrada em `index.tsx` (`viewMode === 'whatsapp'`). Lista os chats monitorados (callable `listWhatsappChats`), mostra a timeline paginada de cada conversa (página 1 viva via `onSnapshot`, anteriores sob demanda — precedente `PersonalDiaryView`), com player de áudio e imagens carregados sob demanda do Storage.
- O usuário seleciona mensagens (máx. 200) e dispara uma **consolidação**: `addDoc` em `whatsapp_consolidacoes` (o write é o RPC — padrão `copilot_jobs`) → trigger `on_whatsapp_consolidacao_created` (main.py, GB_1, 540s) → `functions/whatsapp_consolidation.py:process_consolidation_job`.
- O job: transcreve os áudios (helper `_transcribe_audio_bytes` de `hermes_core_logic.py` — Groq Whisper com fallback Gemini), **cacheando cada transcrição de volta em `whatsapp_messages.transcription_text`**; monta o **transcript literal por código** (nunca pela IA — garantia anti-alucinação); faz UMA chamada de síntese (`GEMINI_BALANCED_MODEL`, feature `whatsapp_consolidation.synthesis`) restrita ao transcript, gerando `resumo`/`itens_de_acao`/`decisoes`; grava um digest vetorizado `consol_{job_id}` em `whatsapp_digests` (mantém `buscar_conversas_whatsapp` do copiloto vivo com dados curados); marca as mensagens com `consolidation_ids`. Progresso e resultado são empurrados por campos no doc do job.
- Áudios sem mídia capturada (worker sem `FIREBASE_STORAGE_BUCKET`) viram `[áudio não capturado]`; >24MB ou formato não suportado são pulados com nota; falha transitória de transcrição não é cacheada (retry funciona).
- **Associação a ação**: no painel do relatório, ações com o chat vinculado (`tarefas.whatsapp_vinculos` — ver abaixo) aparecem pré-sugeridas; um typeahead cobre as demais. Associar grava a nota rica `WHATSAPP::JSON::` no `acompanhamento` da ação (chip verde do `DiarioBordoUI.tsx`) e marca o job com `task_id`/`applied_at`.

### Vínculo manual (contato/grupo → ação) — pré-sugestão de destino

- Botão "Vincular WhatsApp" em `TaskExecutionView.tsx` (seção "Agendamento") abre um seletor de chats conhecidos — busca via `listWhatsappChats` mais um campo de entrada manual de `chat_id` para um chat ainda não monitorado. Seleção multi-contato/grupo, gravada em `tarefas.whatsapp_vinculos[]` (`{chat_id, chat_name, is_group, data_vinculo}`).
- Vincular **não** substitui a allowlist de captura (§1) — se o chat não estiver na allowlist, nenhuma mensagem chega a `whatsapp_messages` e o vínculo fica sem efeito prático.
- Com a triagem automática desligada, o papel principal do vínculo é ser **pré-sugestão de destino** na Caixa de Entrada: consolidações de um chat vinculado oferecem a(s) ação(ões) vinculada(s) no topo do seletor de associação. (O pré-filtro determinístico que o vínculo exercia na triagem permanece no código, dormente — ver abaixo.)

### Triagem automática (legado — dormente atrás do flag)

- Arquivo: `functions/whatsapp_ingest.py`, função `triage_whatsapp_messages` — chamada no fim de `run_full_sync` (mesmo ciclo de 30 min do e-mail). **Desligada desde 2026-08-14** (`system/settings.whatsapp_ingest.enabled = false`) — substituída pela consolidação manual acima; o código permanece funcional caso o flag seja religado.
- Fluxo: mensagens novas desde o cursor (`system/whatsapp_ingest.last_processed_at`) são agrupadas por conversa em janelas; cada janela recebe **uma** chamada de IA (`gemini-3.5-flash-lite`) classificando-a como `acao` (vínculo específico com uma ação ativa/stand-by), `conhecimento` (vale lembrar, sem ação específica) ou `ruido` (descartada, nada é gravado).
- A mesma chamada extrai elementos executivos da janela, para que a consolidação tenha relevância funcional em vez de ser um resumo solto: `itens_de_acao[]` (descrição, responsável, prazo), `decisoes[]` (pontos acordados/definidos — auditoria), `datas_mencionadas[]` e, quando a conversa realmente justifica, `mutacoes_propostas` (novas etapas para o `plano_acao` da ação, ajuste de `data_limite`, um lembrete). `_sanitize_*` em `whatsapp_ingest.py` valida formato (datas `YYYY-MM-DD`) e limita tamanho antes de qualquer gravação.
- Janelas `acao` propõem o vínculo pelo mesmo motor de sugestão usado por e-mail/SIPAC/Calendar (`functions/email_action_linker.py:queue_and_maybe_send_suggestion`) — cartão de confirmação no Telegram (com os itens de ação/decisões/mutação sugerida listados), canal `whatsapp`. O botão "📋 Registrar + aplicar mudanças" (callback `emlink:{id}:mut`) aplica a mutação proposta na tarefa (via `email_action_linker.py:apply_suggestion`) na mesma transação que grava a nota no diário — nunca automaticamente, sempre por confirmação humana, mesmo princípio do resto do motor. A nota gravada usa o envelope rico `WHATSAPP::JSON::{...}` (`src/utils/diaryEntries.ts:buildDiaryWhatsappNote`), renderizado como chip pelo `DiarioBordoUI.tsx` com os itens de ação, decisões e — quando aplicadas — as mudanças feitas na ação.
- Feature flag: `system/settings.whatsapp_ingest.enabled` (padrão desligado — sem efeito enquanto o worker local também não estiver rodando e configurado).
- Pré-filtro por vínculo manual (dormente junto com a triagem): quando o `chat_id` de uma janela tem ação(ões) vinculada(s) em `tarefas.whatsapp_vinculos`, a IA escolhe `task_id` só entre essas candidatas — mesmo espírito do matching determinístico de SIPAC (`processo_sei`) e Calendar (`google_calendar_id`), mantendo a classificação de relevância com a IA.

## 4. Digests vetorizados e busca semântica

- **Produtor atual: o job de consolidação** — cada consolidação grava um digest `consol_{job_id}` (relevancia `consolidacao`), dados curados por humano. A triagem legada gerava digests `{chat_id}_{timestamp}` para janelas `acao`/`conhecimento` (dormente com o flag).
- Campos do digest: `chat_id`, `chat_name`, `resumo`, `topicos[]`, `relevancia`, `n_mensagens`, `inicio`/`fim`, `itens_de_acao[]`, `decisoes[]`, `datas_mencionadas[]`, `embedding` (Vector 768-dim, `gemini-embedding-001` — o texto embeddado também incorpora os itens de ação e decisões, não só resumo/tópicos).
- Mensagens cruas **não** são indexadas individualmente — só o digest da janela, no mesmo padrão de `knowledge_nodes`/`indice_artefatos` (ruidoso e caro demais indexar mensagem a mensagem).
- Tool do copiloto `buscar_conversas_whatsapp(query, limite=5)` — busca vetorial (`find_nearest`, COSINE) em `whatsapp_digests`, implementada em `functions/whatsapp_ingest.py:buscar_conversas_whatsapp` e exposta em `main.py` dentro de `askCopilotoHermes` (gate por protocolo: só entra no prompt quando a conversa menciona "whatsapp"/"zap").
- Índice vetorial declarado em `firestore.indexes.json` (`whatsapp_digests.embedding`, dimensão 768).

## 5. Envio (`whatsapp_outbox`)

- Fila alimentada por `functions/tools/schedule_whatsapp_message.py` (tool do copiloto), pela confirmação `confirm_whatsapp` no Telegram, e pela ponte de voz (`hermes-voice-bridge/tools.py`).
- Dois consumidores coordenados por `system/settings.whatsapp_auto_send_enabled` + o heartbeat do worker (§1): quando habilitado e o worker está vivo (heartbeat ≤ 10 min), o **cron do worker Node** reivindica e envia de verdade via `client.sendMessage`; caso contrário, a Cloud Function `dispatch_scheduled_whatsapp_messages` manda um card no Telegram com link `wa.me` para envio manual.

## Limitações conhecidas

- Automação não-oficial (`whatsapp-web.js`) — sujeita a bloqueio/quebra pelo WhatsApp; sem SLA.
- Só captura mensagens recebidas enquanto o processo está rodando — sem backfill de histórico anterior.
- Transcrição de áudio (`ptt`/`audio`) ainda não implementada — mensagens de voz entram na triagem só pelo texto (vazio) e tipo.
- Upload de mídia ao Storage depende de `FIREBASE_STORAGE_BUCKET` estar configurado no ambiente do worker; sem isso, mídia é capturada só como metadata.
