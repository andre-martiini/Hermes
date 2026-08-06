---
type: integration
title: Integração WhatsApp Cloud API — Processamento de Lote
description: Webhook oficial da Meta que recebe lotes de mensagens do WhatsApp (texto, áudio, vídeo, imagem) encaminhadas pelo usuário, transcreve tudo em ordem cronológica e responde com um resumo — sem depender de nenhum processo rodando localmente.
resource: functions/whatsapp_cloud.py
tags: [hermes, whatsapp, integracao, gemini, firestore, cloud-api]
timestamp: 2026-08-06T00:00:00Z
---

# Integração WhatsApp Cloud API — Processamento de Lote

Diferente da [Integração WhatsApp](/docs/okf/integracoes/whatsapp.md) (microsserviço `whatsapp-web.js`, que precisa de um processo rodando 24/7 com sessão autenticada), esta integração usa a **API oficial da Meta (WhatsApp Business Platform / Cloud API)**. É 100% serverless — roda inteiramente em Cloud Functions — e funciona do celular a qualquer momento, sem nada para manter ligado.

## 1. Como usar

1. Numa conversa do WhatsApp, selecione o lote de mensagens (texto, áudio, vídeo, imagem) que quer processar.
2. Encaminhe (`Encaminhar`) o lote inteiro para o número vinculado ao Hermes, mantendo a ordem original.
3. Envie `#resumo` (ou apenas `resumo`) para fechar o lote. Opcionalmente acrescente uma instrução: `#resumo focar nas datas mencionadas`.
4. O Hermes responde no próprio WhatsApp com duas mensagens: o **resumo** e, em seguida, a **transcrição completa** na ordem cronológica original.

Mensagens que chegam antes do `#resumo` só ficam na fila — nada é processado (nem transcrito, nem gasta chamada de IA) até o gatilho de fechamento chegar.

## 2. Arquitetura

- Arquivo: `functions/whatsapp_cloud.py`
- Duas Cloud Functions:
  - `whatsappCloudWebhook` (HTTP request) — porteiro rápido. Valida a assinatura do payload (`X-Hub-Signature-256`), filtra pelo número autorizado, baixa mídia da Graph API e grava cada mensagem em `whatsapp_cloud_inbound`. Nunca aguarda transcrição/Gemini.
  - `on_whatsapp_cloud_inbound` (Firestore trigger em `whatsapp_cloud_inbound/{docId}`) — só age quando o documento criado é a mensagem de fechamento (`#resumo`). Reivindica transacionalmente todo o lote pendente do remetente (evita processar duas vezes sob retry), monta a transcrição em ordem cronológica (pelo timestamp original do WhatsApp, não o de chegada no Firestore), resume com Gemini e responde via Graph API.
- Reaproveita o pipeline de transcrição já existente do Hermes: `_transcribe_audio_bytes` (Groq Whisper com fallback Gemini) de `hermes_core_logic.py`. Vídeo tem a faixa de áudio extraída via FFmpeg antes de transcrever, igual à função `transcreverAudio`.
- Imagens recebem uma descrição objetiva via Gemini multimodal (inclui OCR leve de texto visível).
- Documentos (PDF, etc.) por enquanto **não** têm o conteúdo extraído — entram na transcrição só como referência (nome + tipo). Ver limitações abaixo.

## 3. Configuração — sem CNPJ, dois níveis possíveis

A verificação comercial da Meta (que pede CNPJ) só é exigida para escalar volume. Para uso pessoal (1 destinatário — você mesmo) não é necessária:

### Nível 1 — Número de teste (recomendado para começar)

1. Acesse [developers.facebook.com](https://developers.facebook.com/) → crie um app → adicione o produto **WhatsApp**.
2. No painel do produto WhatsApp, a Meta já fornece um **número de teste gratuito** e um token temporário — sem CNPJ.
3. Em "To" → "Manage phone number list", adicione o **seu próprio número** (com código do país) como destinatário autorizado. O número de teste só conversa com até 5 números cadastrados aqui — irrelevante no seu caso, já que o Hermes só fala com você.
4. Anote: `Phone number ID` (painel do produto WhatsApp) e o **token de acesso**.

### Nível 2 — Número próprio sem verificação (para uso de mais longo prazo)

Depois de validar o fluxo no nível 1, dá pra vincular um número de telefone próprio (chip dedicado) à mesma conta, sem completar a verificação comercial — fica no tier inicial de até 250 contatos únicos/dia, mais que suficiente para 1 usuário. Só o `Phone number ID` e o token mudam; todo o resto (webhook, código) é idêntico.

### Configurar o webhook

1. No painel do app Meta → **WhatsApp → Configuration → Webhook**, defina:
   - **Callback URL**: a URL pública da function `whatsappCloudWebhook` (formato `https://<região>-<projeto>.cloudfunctions.net/whatsappCloudWebhook`, disponível após o deploy).
   - **Verify token**: uma string qualquer que você escolher (ex.: gerada com `openssl rand -hex 20`) — precisa ser a mesma salva em `whatsapp_cloud_verify_token` (passo abaixo).
2. Clique em **Verify and save** — a Meta faz um `GET` de handshake que a function responde automaticamente.
3. Em **Webhook fields**, inscreva-se em `messages`.
4. (Recomendado) Em **App settings → Basic**, copie o **App Secret** — usado para assinar os payloads e validar que vieram mesmo da Meta.

### Salvar as chaves no Firestore

No documento `system/api_keys`, adicione os campos:

| Campo | Valor |
|---|---|
| `whatsapp_cloud_token` | Token de acesso (do painel do produto WhatsApp) |
| `whatsapp_cloud_phone_number_id` | Phone number ID |
| `whatsapp_cloud_verify_token` | O verify token escolhido no passo do webhook |
| `whatsapp_cloud_app_secret` | App Secret (opcional, mas recomendado — habilita a verificação de assinatura) |
| `whatsapp_cloud_allowed_number` | Seu número, só dígitos, com código do país (ex.: `5527999999999`) — único remetente autorizado |

### Deploy

```bash
cd functions
firebase deploy --only functions:whatsappCloudWebhook,functions:on_whatsapp_cloud_inbound,firestore:indexes
```

O índice composto em `whatsapp_cloud_inbound` (`sender` + `processed` + `wa_timestamp`) já está declarado em `firestore.indexes.json` — o `--only firestore:indexes` acima cria ele. Sem o índice, a primeira tentativa de fechar um lote falha com um erro do Firestore que inclui um link para criá-lo manualmente.

## 4. Limitações conhecidas

- **Token de teste tem validade curta** (Nível 1) e pode precisar ser renovado periodicamente no painel Meta — o Nível 2 (número próprio) usa token de sistema de longa duração.
- **Documentos (PDF/DOCX/etc.) não têm o conteúdo extraído automaticamente** nesta versão — aparecem na transcrição só como referência de nome/tipo. Dá pra estender reaproveitando `pdf_precision.py`, que já existe no projeto.
- **Sem verificação de assinatura se `whatsapp_cloud_app_secret` não for configurado** — o webhook loga um aviso e segue sem validar a origem do payload (ainda protegido pelo filtro de número autorizado). Configurar o App Secret é fortemente recomendado.
- **Teto de 150 itens por lote**: lotes maiores processam os 150 mais antigos e avisam que o resto ficou pendente para um próximo `#resumo`.
- **Mensagens editadas/reações/figurinhas/localização/contato** são ignoradas silenciosamente (fora do escopo desta ferramenta).

## 5. Coleções Firestore

Ver [Schema do Firestore](/docs/okf/arquitetura/schema-firestore.md) para `whatsapp_cloud_inbound` e `whatsapp_cloud_batches`.
