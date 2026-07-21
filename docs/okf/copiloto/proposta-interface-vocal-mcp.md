---
type: proposta
title: Interface Vocal Híbrida + Servidor MCP — Proposta Consolidada
description: Avaliação da proposta de interface vocal (STT/TTS local + Gemini + MCP) confrontada com o estado atual do Hermes, e proposta final revisada.
tags: [hermes, okf, copiloto, voz, mcp, arquitetura]
timestamp: 2026-07-21T00:00:00-03:00
---

# Interface Vocal Híbrida + Servidor MCP — Proposta Consolidada

Este documento avalia a proposta original de "Interface Vocal Híbrida e Servidor MCP"
(pipeline local STT/TTS + Gemini Flash-Lite + servidor MCP serverless) contra o estado
real do repositório, registra os problemas encontrados na verificação ponta a ponta e
apresenta a **proposta final revisada**.

## 1. Confronto com o estado atual do Hermes

A proposta original assume um cenário quase greenfield. O repositório mostra outra
realidade:

| Premissa da proposta | Estado real do repositório |
|---|---|
| "Criar" a camada de voz do zero | Já existe `hermes-voice-bridge/` (FastAPI, Cloud Run): canal telefônico via Twilio Media Streams e canal navegador via WebSocket, ambos usando **Gemini Live API** (`gemini-3.1-flash-live-preview`, speech-to-speech nativo, sem STT/TTS separados) |
| Servidor MCP a criar no backend | **Não existe nada de MCP** no repo; o tool-calling é function calling nativo (Gemini no copiloto web/Telegram, Claude no Godmode) |
| Tool discovery dinâmica necessária | Existe um registry central rico: `functions/tools/registry.py` com ~42 tools, schemas JSON por tool (`functions/tools/schemas/*.json`), gating de confirmação (`_NEEDS_CONFIRMATION`), tools assíncronas via Pub/Sub (`_ASYNC_TOOLS`) |
| Copiloto acessível por rota HTTP REST | O copiloto principal é o callable Firebase `askCopilotoHermes` (`functions/main.py:7029`), com RAG híbrido, memória de sessão em Firestore (`sessoes_copiloto`), persona (`system/copilot_soul`), perfil do usuário e protocolos de gating |
| Autenticação a definir (Firebase ID Token) | Web usa Firebase Auth via callables; o voice-bridge atual usa **senha falada** validada contra a transcrição (frágil); Telegram usa whitelist de chat_id |
| Memória = FIFO de 4–6 turnos no cliente | O Hermes já tem memória de sessão server-side (`sessoes_copiloto`), memória global (`knowledge_nodes`), POPs e perfil deduzido do usuário |
| Gemini 3.1 Flash-Lite | Coerente: o copiloto já usa `gemini-3.1-flash-lite` (chat) com escalada para `gemini-3.5-flash` em prompts complexos (`gemini_cost_controls.py`) |
| STT/TTS inexistentes | Backend já transcreve com **Groq Whisper-Large-V3-Turbo** (fallback Gemini) e sintetiza TTS com `gemini-2.5-flash-preview-tts` (canal Telegram); frontend tem Web Speech API e MediaRecorder |

**Diagnóstico central:** o problema real do Hermes hoje não é ausência de voz — é
**fragmentação de cérebros**. Existem quatro orquestradores paralelos (copiloto web
Gemini, Godmode Claude, router Telegram, voice-bridge Live), e o voice-bridge duplica à
mão 7 tools somente-leitura que já derivaram do catálogo oficial de 42. A proposta
original, como está, criaria um **quinto** cérebro com um **segundo** catálogo. O valor
dela está no servidor MCP como fonte única de ferramentas — desde que gerado a partir do
registry existente, não de um catálogo novo.

## 2. Verificação ponta a ponta — problemas encontrados

1. **Search Grounding + Function Calling (Módulo B):** a base de conhecimento do próprio
   projeto (`docs/okf/integracoes/gemini-models.md`) registra `400 INVALID_ARGUMENT` ao
   combinar function calling customizado com a tool nativa de Google Search em modelos
   Flash-Lite. A proposta declara as duas capacidades simultaneamente ativas. Além do
   risco técnico, o backend já possui `pesquisar_internet` e `ler_pagina_web` como tools
   — acesso à internet deve vir por elas (centraliza custo, log e auditoria).

2. **Barge-in sem AEC não funciona:** com microfone aberto durante a reprodução do TTS,
   o VAD detecta o próprio alto-falante e o sistema se auto-interrompe. É obrigatório
   cancelamento de eco acústico (WebRTC APM / `speexdsp`) ou, no mínimo, supressão do
   VAD ponderada pelo sinal de referência do TTS. A proposta não menciona AEC.

3. **Erros na matriz de tecnologia:**
   - *distil-whisper* (`distil-medium`) é **inglês-only** — inutilizável para pt-BR.
     Usar `faster-whisper` multilingual: `small` (~0,5 GB int8) ou `large-v3-turbo`
     int8 (~1,5 GB, muito melhor em pt-BR; cabe na RTX 3050 de 4 GB).
   - *Edge-TTS* **não é local** — é serviço cloud da Microsoft; contradiz a premissa de
     "processamento de voz local / custo zero de transmissão".
   - *Kokoro-82M* tem suporte a pt-BR limitado (vozes `pf_dora`/`pm_alex`, qualidade
     média). Alternativa leve e sólida em pt-BR: **Piper** (CPU, latência baixa).
     Recomendação: iniciar com Piper ou Kokoro pt e validar por escuta.

4. **Tools mutantes ignoradas:** o catálogo tem 15 tools que exigem confirmação
   (draft-and-approve) — criar ação, registrar transação financeira, enviar WhatsApp
   etc. A proposta trata todas as tools como equivalentes. Um canal de voz **precisa**
   herdar esse gating, com confirmação falada explícita antes de `tools/call` em
   qualquer tool marcada como `needs_confirmation`.

5. **Tools assíncronas não cabem em HTTP POST síncrono:** `buscar_e_analisar_email`,
   `gerar_relatorio`, `ler_documento_na_integra` etc. rodam via worker Pub/Sub. O
   transporte proposto (POST síncrono stateless) precisa de um contrato de job
   (`jobId` + polling) ou essas tools ficam fora do canal de voz na fase 1.

6. **Quinto cérebro / memória desconectada:** com FIFO local de 4–6 turnos e chamada
   direta ao Gemini, o cliente de voz perde persona (`copilot_soul`), perfil do
   usuário, memórias globais, POPs e continuidade com as sessões web
   (`sessoes_copiloto`). Isso repete o erro do voice-bridge atual. O MCP resolve se
   expuser, além de tools, o **contexto** (equivalente ao `context.py` do bridge) e a
   **persistência de sessão**.

7. **Autenticação:** usar Firebase ID Token é correto (e melhor que a senha falada do
   bridge atual), mas exige: verificação server-side com Admin SDK, whitelist de UID
   autorizado (sistema é single-user na prática), refresh token guardado em keyring do
   SO (não em `.env` plano), e rate limiting no endpoint.

8. **Latências otimistas:** a tabela soma ~2,1–2,9 s por turno sem contar cold start de
   Cloud Run/Functions (Python + 2 GB pode passar de 5 s frio), nem TTFT real do LLM.
   Com `min-instances=0` a primeira interação do dia será lenta; documentar ou usar
   `min-instances=1` no serviço MCP (custo baixo em instância pequena).

9. **VAD 1,0–1,2 s:** aceitável como padrão; prever endpointing adaptativo (encurtar
   para ~0,6 s quando a transcrição parcial termina em frase completa) como refinamento.

10. **Pontos corretos da proposta** (a preservar): topologia híbrida (áudio local +
    raciocínio cloud) é mais barata que Gemini Live API para uso em desktop; modelo
    `gemini-3.1-flash-lite` coincide com o já usado; JSON-RPC 2.0 stateless sobre HTTP
    é aderente ao transporte **Streamable HTTP** do MCP atual; hospedagem em Cloud Run
    é coerente com a infra existente (o voice-bridge já está lá).

## 3. Proposta final revisada

### Princípio norteador

> **Um cérebro, um catálogo, N canais.** O servidor MCP é gerado a partir de
> `functions/tools/registry.py` (fonte única). O cliente de voz local é mais um canal
> de I/O — como Telegram e WhatsApp — e não um novo orquestrador isolado.

### Arquitetura

```
┌──────────────────────────── CLIENTE LOCAL (PC, RTX 3050) ────────────────────────────┐
│ UI web em localhost (navegador): forma de onda + chat de texto + mic com AEC nativo  │
│         │ áudio (WebSocket)                          ▲ áudio TTS + transcrições      │
│         ▼                                            │                               │
│ [Silero VAD] → [faster-whisper large-v3-turbo int8] → [Orquestrador FastAPI]         │
│                            [Piper/Kokoro pt-BR, síntese por sentença] ──┘            │
│                                    histórico FIFO 6–8 turnos + persistência remota   │
└──────────────────────────────────────────────┬───────────────────────────────────────┘
                                               │ HTTPS
                    ┌──────────────────────────┼──────────────────────────┐
                    ▼                          ▼                          │
        Gemini API (gemini-3.1-flash-lite;     Servidor MCP (Cloud Run,   │
        escalada p/ 3.5-flash em turnos        Streamable HTTP, SDK       │
        complexos; SEM grounding nativo —      oficial) — Firebase ID     │
        internet via tool pesquisar_internet)  Token + whitelist de UID   │
                                               │ reusa registry + schemas │
                                               ▼                          │
                                    Firestore / Cloud Functions (Hermes)──┘
```

### Módulo C — Servidor MCP (construir primeiro)

- Serviço dedicado em **Cloud Run** (`southamerica-east1`), SDK MCP oficial Python
  (FastMCP), transporte **Streamable HTTP** (`POST /mcp`), stateless.
- **Gerado do registry existente**: `tools/list` serializa `_CATALOG` +
  `schemas/*.json`; anota em `_meta` os flags `needs_confirmation` e `is_async`, e um
  novo flag `voice_enabled` no registry para excluir do canal de voz tools que não fazem
  sentido faladas (ex.: `gerar_rascunho_formulario`).
- **Resources MCP**: `hermes://voice-context` (persona + perfil + memórias recentes —
  reaproveitar a lógica de `hermes-voice-bridge/context.py`) e
  `hermes://session/{id}` (histórico em `sessoes_copiloto`, para continuidade entre voz
  e web).
- **Tools async**: `tools/call` retorna `{jobId, status:"processing"}` e expõe
  `consultar_job(jobId)` para polling.
- **Auth**: `Authorization: Bearer <Firebase ID Token>`, verificado com Admin SDK +
  whitelist de UID em Firestore; rate limiting; log de auditoria de cada `tools/call`
  (tool, args, uid, canal) em Firestore.
- `min-instances=1` para eliminar cold start no caminho crítico.

### Módulo A — Cliente local com interface visual

Decisão registrada (2026-07-21): a prioridade é **redução de custos**, portanto o
processamento de áudio fica local (GPU RTX 3050). O requisito de experiência é abrir
uma **interface que mostra o sinal de voz** e permite conversar tanto por voz quanto
por texto, como um chatbot comum — não um script headless.

- **Arquitetura do cliente**: orquestrador Python 3.11+ (FastAPI) rodando em
  `localhost`, servindo uma **UI web local** aberta no navegador. A UI tem: forma de
  onda ao vivo (Web Audio API `AnalyserNode` + canvas), histórico do chat, campo de
  texto (mensagens digitadas pulam o STT) e botão/hotkey de microfone.
- **Captura de áudio no navegador** via `getUserMedia({echoCancellation: true})` —
  o AEC nativo do Chrome resolve o problema do barge-in sem WebRTC APM manual; o áudio
  segue por WebSocket para o orquestrador local.
- Pipeline no orquestrador: Silero VAD (silêncio 1,0 s, endpointing adaptativo depois)
  → faster-whisper **`large-v3-turbo` int8** (`language="pt"`, ~1,5 GB VRAM; fallback
  `small` ~0,5 GB) → loop LLM/MCP → TTS **Piper pt-BR** (CPU) ou Kokoro pt (GPU), com
  **síntese por sentença**, reproduzida na UI.
- **Barge-in**: mic ativo durante TTS (eco cancelado pelo navegador); nova fala válida
  cancela a reprodução **e** a geração LLM em andamento.
- Fase inicial em **push-to-talk** para validar o pipeline antes de ligar VAD/barge-in.
- Refresh token do Firebase no **keyring do SO**; renovação do ID token via Firebase
  Auth REST.

**Caminho de evolução para online**: como a UI já é web e o servidor MCP já é cloud,
migrar para o formato online (dentro do web app do Hermes) significa apenas portar o
componente de UI para o React do Hermes e trocar o processamento local de áudio por um
serviço na nuvem (Gemini Live ou STT/TTS gerenciado) — o cérebro, o catálogo e a
interface permanecem os mesmos.

### Módulo B — Raciocínio

- `gemini-3.1-flash-lite` como padrão (mesmo modelo do copiloto), com a mesma
  heurística de escalada para `gemini-3.5-flash` em turnos complexos.
- **Sem Google Search Grounding nativo** (conflito documentado com function calling em
  Flash-Lite); internet via tools `pesquisar_internet` / `ler_pagina_web` do MCP.
- System prompt = resource `hermes://voice-context` + instruções de brevidade vocal
  (herdar do `_build_system_instruction` do bridge atual).
- Memória: FIFO local de 6–8 turnos como cache; ao encerrar sessão (ou a cada N
  turnos), persistir em `sessoes_copiloto` via MCP para continuidade entre canais.
- **Confirmação falada obrigatória** antes de qualquer tool `needs_confirmation`:
  o orquestrador intercepta a function call, verbaliza a proposta ("Vou criar a ação X
  com prazo Y — confirma?") e só chama `tools/call` após "sim" explícito.
- Feedback auditivo imediato ("Verificando no Hermes…") disparado localmente ao
  detectar a function call — mantido da proposta original.

### Fases de implementação

1. **Servidor MCP** sobre o registry (tools/list, tools/call, resources, auth, auditoria)
   + flag `voice_enabled` no registry. *Critério de aceite: chamar
   `consultar_historico_acoes` via MCP com ID token válido.*
2. **Cliente local mínimo** com UI web em localhost (forma de onda, chat de texto,
   push-to-talk): whisper → Gemini → tools MCP → TTS.
   *Aceite: "quais minhas tarefas de hoje?" respondido por voz em < 4 s, com a
   transcrição e a resposta visíveis no chat.*
3. **VAD + barge-in + AEC** e endpointing adaptativo; persistência de sessão e
   confirmação falada para tools mutantes.
4. **Convergência do voice-bridge**: migrar o canal Twilio (que continua precisando de
   Gemini Live, pois roda server-side sem GPU local) para consumir o MCP e o resource de
   contexto, **apagando** `hermes-voice-bridge/tools.py` duplicado. O canal navegador do
   bridge pode ser aposentado em favor do cliente local.

### Latências realistas (turno com 1 tool, serviço quente)

| Etapa | Estimativa |
|---|---|
| Silêncio VAD | 1,0 s |
| STT local (GPU) | 0,15–0,4 s |
| LLM (1ª chamada, TTFT + function call) | 0,5–1,0 s |
| Execução MCP (Cloud Run + Firestore) | 0,3–0,8 s |
| LLM (2ª chamada, resposta) | 0,5–1,0 s |
| TTS 1ª sentença | 0,2–0,5 s |
| **Total até início da fala** | **~2,7–4,7 s** (com feedback auditivo intermediário em ~2 s) |

### Riscos remanescentes

- Qualidade de TTS local em pt-BR exige validação por escuta (Piper vs Kokoro) antes de
  fechar a escolha.
- Tools async por voz têm UX inerentemente ruim (relatórios longos); manter fora do
  canal de voz até haver mecanismo de notificação proativa.
- Whitelist de UID e auditoria são pré-requisitos de segurança antes de expor qualquer
  tool mutante via MCP público.
