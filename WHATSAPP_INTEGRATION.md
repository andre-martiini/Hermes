# Integração WhatsApp no Hermes

## 1) Microsserviço de captura

- Local: `services/whatsapp-capture`
- Stack: `whatsapp-web.js` + `firebase-admin` + transcrição Groq Whisper.
- Execução:

```bash
cd services/whatsapp-capture
npm install
npm run start
```

## 2) Armazenamento no Firebase

- Coleção Firestore: `whatsapp_messages`
- Campos principais:
  - `id`, `wa_message_id`, `contact_name`, `contact_name_normalized`
  - `timestamp`, `message_type`, `content`, `links`
  - `media` (`url`, `fileName`, `mimeType`, `path`, `sizeBytes`)
  - `transcription_text`, `transcription_model`

## 3) Consulta com Gemini 2.5 Flash-Lite

- Arquivo: `src/utils/whatsappAssistant.ts`
- Fluxo:
  1. Gemini interpreta comando e aciona tool `search_whatsapp_messages`.
  2. Frontend executa query no Firestore com os parâmetros extraídos.
  3. Resultados multimodais viram contexto para síntese final em markdown.
  4. Resposta cita anexos com marcador `[ARQ-N]`.

## 4) UI React

- Componente: `src/components/tools/WhatsAppAssistantTool.tsx`
- Acesso: menu de Ferramentas → **Assistente WhatsApp**.
- Recursos:
  - Campo de comando em linguagem natural.
  - Renderização markdown simples com links clicáveis.
  - Botões de download para anexos retornados/referenciados.
