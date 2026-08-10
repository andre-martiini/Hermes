---
type: integration
title: Integração WhatsApp no Hermes
description: Microsserviço de captura de mensagens WhatsApp, triagem por IA com vínculo a ações e busca semântica via digests vetorizados.
resource: services/whatsapp-capture
tags: [hermes, whatsapp, integracao, gemini, firestore]
timestamp: 2026-08-08T00:00:00-03:00
---

# Integração WhatsApp no Hermes

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
- Campos: `chat_id`, `chat_name`, `is_group`, `author_name`, `from_me`, `wa_message_id`, `timestamp` (quando a mensagem foi enviada no WhatsApp), `ingested_at` (quando o worker gravou — usado como cursor de processamento), `message_type`, `content`, `links[]`, `media` (`mimeType`, `sizeBytes`, `storage_path` se o upload ao Storage funcionou), `transcription_text`/`transcription_model` (reservados — transcrição de áudio ainda não implementada).
- Captura tanto mensagens recebidas quanto enviadas (`from_me`), via um único listener em `message_create`.

## 3. Triagem e vínculo com ações

- Arquivo: `functions/whatsapp_ingest.py`, função `triage_whatsapp_messages` — chamada no fim de `run_full_sync` (mesmo ciclo de 30 min do e-mail).
- Fluxo: mensagens novas desde o cursor (`system/whatsapp_ingest.last_processed_at`) são agrupadas por conversa em janelas; cada janela recebe **uma** chamada de IA (`gemini-3.5-flash-lite`) classificando-a como `acao` (vínculo específico com uma ação ativa/stand-by), `conhecimento` (vale lembrar, sem ação específica) ou `ruido` (descartada, nada é gravado).
- A mesma chamada extrai elementos executivos da janela, para que a consolidação tenha relevância funcional em vez de ser um resumo solto: `itens_de_acao[]` (descrição, responsável, prazo), `decisoes[]` (pontos acordados/definidos — auditoria), `datas_mencionadas[]` e, quando a conversa realmente justifica, `mutacoes_propostas` (novas etapas para o `plano_acao` da ação, ajuste de `data_limite`, um lembrete). `_sanitize_*` em `whatsapp_ingest.py` valida formato (datas `YYYY-MM-DD`) e limita tamanho antes de qualquer gravação.
- Janelas `acao` propõem o vínculo pelo mesmo motor de sugestão usado por e-mail/SIPAC/Calendar (`functions/email_action_linker.py:queue_and_maybe_send_suggestion`) — cartão de confirmação no Telegram (com os itens de ação/decisões/mutação sugerida listados), canal `whatsapp`. O botão "📋 Registrar + aplicar mudanças" (callback `emlink:{id}:mut`) aplica a mutação proposta na tarefa (via `email_action_linker.py:apply_suggestion`) na mesma transação que grava a nota no diário — nunca automaticamente, sempre por confirmação humana, mesmo princípio do resto do motor. A nota gravada usa o envelope rico `WHATSAPP::JSON::{...}` (`src/utils/diaryEntries.ts:buildDiaryWhatsappNote`), renderizado como chip pelo `DiarioBordoUI.tsx` com os itens de ação, decisões e — quando aplicadas — as mudanças feitas na ação.
- Feature flag: `system/settings.whatsapp_ingest.enabled` (padrão desligado — sem efeito enquanto o worker local também não estiver rodando e configurado).

## 4. Digests vetorizados e busca semântica

- Janelas `acao`/`conhecimento` (não `ruido`) geram um **digest** em `whatsapp_digests/{chat_id}_{timestamp}`: `chat_id`, `chat_name`, `resumo`, `topicos[]`, `relevancia`, `n_mensagens`, `inicio`/`fim`, `itens_de_acao[]`, `decisoes[]`, `datas_mencionadas[]`, `embedding` (Vector 768-dim, `gemini-embedding-001` — o texto embeddado também incorpora os itens de ação e decisões, não só resumo/tópicos).
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
