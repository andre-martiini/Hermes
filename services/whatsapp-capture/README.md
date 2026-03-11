# Hermes WhatsApp Capture Service

Microsserviço Node.js isolado para capturar mensagens recebidas no WhatsApp, armazenar no Firebase e transcrever áudios via Groq Whisper.

## Recursos

- Autenticação com QR Code no terminal (`whatsapp-web.js`).
- Captura em tempo real de texto, links, imagens, documentos e áudios.
- Upload de mídia para Firebase Storage.
- Persistência de metadados em `whatsapp_messages` no Firestore.
- Transcrição de áudio com `whisper-large-v3-turbo` (Groq).

## Variáveis de ambiente

- `GROQ_API_KEY` (obrigatória)
- `FIREBASE_STORAGE_BUCKET` (recomendada)
- `FIREBASE_SERVICE_ACCOUNT_JSON` (JSON completo como string, opcional)
- `GOOGLE_APPLICATION_CREDENTIALS` (alternativa ao JSON inline)
- `WHATSAPP_SESSION_PATH` (opcional, padrão: `.wwebjs_auth`)
- `WHATSAPP_MESSAGES_COLLECTION` (opcional, padrão: `whatsapp_messages`)

## Execução

```bash
cd services/whatsapp-capture
npm install
npm run start
```

Ao iniciar, escaneie o QR Code no terminal com sua conta pessoal.
