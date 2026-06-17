---
type: integration
title: Integração WhatsApp no Hermes
description: Microsserviço de captura de mensagens WhatsApp, armazenamento em Firestore e assistente de consulta via Gemini.
resource: services/whatsapp-capture
tags: [hermes, whatsapp, integracao, gemini, firestore]
timestamp: 2026-05-19T17:30:42-03:00
---

# Integração WhatsApp no Hermes

## 1. Microsserviço de captura

- Local: `services/whatsapp-capture`
- Stack: `whatsapp-web.js` + `firebase-admin` + transcrição Groq Whisper.
- Execução:
  ```bash
  cd services/whatsapp-capture
  npm install
  npm run start
  ```

## 2. Armazenamento no Firebase

- Coleção Firestore: `whatsapp_messages`
- Campos principais: `id`, `wa_message_id`, `contact_name`, `contact_name_normalized`, `timestamp`, `message_type`, `content`, `links`, `media` (`url`, `fileName`, `mimeType`, `path`, `sizeBytes`), `transcription_text`, `transcription_model`.

## 3. Consulta com Gemini 2.5 Flash-Lite

- Arquivo: `src/utils/whatsappAssistant.ts`
- Fluxo:
  1. Gemini interpreta o comando e aciona a tool `search_whatsapp_messages`.
  2. Frontend executa a query no Firestore com os parâmetros extraídos.
  3. Resultados multimodais entram como contexto para síntese final em markdown.
  4. Resposta cita anexos com marcador `[ARQ-N]`.

Ver preferências de modelo Gemini em [Modelos Gemini disponíveis e preferências](/docs/okf/integracoes/gemini-models.md).

## 4. UI React

- Componente: `src/components/tools/WhatsAppAssistantTool.tsx`
- Acesso: menu de Ferramentas → Assistente WhatsApp.
- Recursos: campo de comando em linguagem natural, renderização markdown com links clicáveis, botões de download para anexos referenciados.
