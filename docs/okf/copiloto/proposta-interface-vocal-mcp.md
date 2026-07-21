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
   `consultar_historico_acoes` via MCP com ID token válido.* ✅ **Implementado**
   (ver seção 4 abaixo — `functions/mcp_server.py`, branch
   `claude/hermes-vocal-interface-review-3wdf6x`).
2. **Cliente local mínimo** com UI web em localhost (forma de onda, chat de texto,
   push-to-talk): whisper → Gemini → tools MCP → TTS.
   *Aceite: "quais minhas tarefas de hoje?" respondido por voz em < 4 s, com a
   transcrição e a resposta visíveis no chat.* ✅ **Implementado** (ver seção 5 —
   `hermes-voice-client/`, mesmo branch). Latência real (< 4s) não pôde ser medida
   nesta fase por falta de credenciais reais no ambiente de implementação; a
   mecânica ponta a ponta foi verificada por outras vias (ver seção 5).
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

## 4. Fase 1 implementada — servidor MCP

Implementado sobre o `functions/tools/registry.py` existente, **como Cloud Function
Python dentro do codebase já deployado** (`functions/`), e não como serviço Cloud Run
separado — decisão tomada em cima da priorização de custo: reaproveita o deploy, a
inicialização do Firebase Admin e o auth já existentes, sem `min-instances` adicional.

### Arquivos novos/alterados

- `functions/mcp_server.py` — Cloud Function HTTP `mcpServer`, JSON-RPC 2.0 síncrono
  sobre POST (`initialize`, `tools/list`, `tools/call`, `resources/list`,
  `resources/read`); GET retorna um health-check simples.
- `functions/tools/mcp_dispatch.py` — executores das tools MCP-enabled, fora de
  qualquer closure (ver nota de escopo abaixo).
- `functions/copilot_context.py` — monta o resource `hermes://voice-context`
  (persona + perfil do usuário autenticado + memórias recentes), adaptado de
  `hermes-voice-bridge/context.py` para usar o uid do ID token em vez de env var.
- `functions/tools/registry.py` — novos `_MCP_ENABLED` / `_VOICE_ENABLED` +
  `is_mcp_enabled()`, `is_voice_enabled()`, `list_mcp_enabled_tools()`.
- `functions/main.py` — **uma única linha adicionada** (`from mcp_server import
  mcpServer`), para não arriscar tocar no arquivo de 13,8 mil linhas do copiloto web.

### Escopo real desta fase (importante)

As ~42 tools do catálogo majoritariamente vivem como *closures* dentro de
`askCopilotoHermes`, presas ao escopo da requisição (`db`, `session_id`, `user_uid`,
`gemini_key` fechados por closure). Não é seguro nem seria honesto expor todas via
`tools/list` fingindo que funcionam. Por isso a fase 1 liga de verdade **4 tools**,
todas somente-leitura ou puras, sem dependência de estado de sessão:

- `consultar_historico_acoes`, `buscar_arquivos_acervo`, `buscar_contato`, `calculadora`

`tools/list` retorna **apenas** essas — listar uma tool que falha ao ser chamada seria
pior do que não listá-la. A lógica de busca em si (`buscar_tarefas`, `buscar_acervo`) é
100% reaproveitada dos módulos já existentes em `functions/tools/`; apenas o
"encaixe"/formatação em torno delas foi replicado de `main.py` para fora do closure —
duplicação deliberada e pequena (~80 linhas), documentada no topo de `mcp_dispatch.py`
como débito técnico a convergir quando `main.py` for refatorado.

Novas tools entram no MCP adicionando: schema em `tools/schemas/`, executor em
`mcp_dispatch.py` e o nome em `registry._MCP_ENABLED`. Tools que exigem confirmação
(`registry.needs_confirmation`) já são bloqueadas em `tools/call` até a chamada trazer
`arguments._confirmed = true` — pronto para quando tools mutantes forem migradas.

### Contrato de auth e configuração necessária antes do deploy

- Header obrigatório: `Authorization: Bearer <Firebase ID Token>`.
- Whitelist de UID: documento Firestore `system/mcp_access` com campo
  `allowed_uids: ["<seu-uid-firebase>"]`, **ou** env var `HERMES_MCP_ALLOWED_UIDS`
  (lista separada por vírgula) nas configurações da função. **Sem nenhum dos dois
  configurados, o acesso é negado por padrão (fail closed)** — este documento não cria
  o doc/env var automaticamente, é um passo manual antes do primeiro uso.
- Auditoria: cada `tools/call` grava um doc em `mcp_audit_log` (uid, tool, argumentos,
  latência). Rate limit é *best-effort* em memória por instância (60 chamadas/min por
  uid) — aceitável para uso single-user; se o MCP ganhar mais clientes, mover para
  contador em Firestore.

### Verificação feita nesta fase

Testado localmente (fora do Firebase, com Firestore/Auth stubados) via `werkzeug` +
contexto Flask simulando o ciclo de request do Functions Framework: `main.py` importa
com a nova função registrada; `tools/list` retorna o schema correto das 4 tools;
`tools/call` executa `calculadora` corretamente (`10*4` → `40`); tool desconhecida e
requisição sem token retornam os erros JSON-RPC esperados (`-32003` e `-32001`
respectivamente); gating de confirmação testado isoladamente. **Não testado**: chamada
real contra Firestore de produção, nem deploy real no Cloud Functions (exige
`firebase deploy --only functions:python` e as credenciais do projeto).

### Próximos passos (fase 3 e além)

1. Configurar `system/mcp_access.allowed_uids` (ou a env var) no projeto real e rodar
   `firebase deploy --only functions:python`.
2. Testar `tools/call consultar_historico_acoes` contra dados reais.
3. ~~Iniciar o cliente local (Módulo A da fase 2)~~ — feito, ver seção 5.
4. Medir a latência real ("< 4s") com credenciais reais (Firebase, Gemini, MCP
   deployado) — não foi possível neste ambiente de implementação.
5. Validar por escuta a qualidade da voz Piper pt-BR (`pt_BR-faber-medium` vs
   alternativas) e trocar o default se necessário.
6. Fase 3: VAD contínuo + barge-in (a captura hoje é só push-to-talk) e persistência
   de sessão entre reinícios do cliente local.
7. Migrar mais tools para `mcp_dispatch.py` conforme a necessidade do cliente de voz
   for exigindo (ex.: `consultar_agenda`, `criar_acao_no_sistema` já com o gating de
   confirmação pronto para recebê-la).

## 5. Fase 2 implementada — cliente local (`hermes-voice-client/`)

Novo diretório self-contained, paralelo a `hermes-voice-bridge/` (que continua servindo
o canal Twilio/Gemini Live e não foi alterado). Não é deployado ao Firebase — roda na
máquina do usuário via `uvicorn main:app`.

### Arquivos

- `main.py` — FastAPI: serve a UI estática e o WebSocket `/ws` (protocolo JSON de
  controle + frames binários PCM16 para áudio, nos dois sentidos).
- `stt.py` — faster-whisper (`WHISPER_MODEL`, padrão `large-v3-turbo` int8, baixado na
  1ª execução).
- `tts.py` — Piper (`PIPER_VOICE`, padrão `pt_BR-faber-medium`), síntese frase a frase,
  baixa a voz na 1ª execução via `piper.download_voices`.
- `orchestrator.py` — `VoiceSession`: `client.chats.create` do Gemini com
  `automatic_function_calling` desabilitado e loop manual de `function_calls`,
  espelhando fielmente o padrão já usado em `functions/main.py::askCopilotoHermes`
  — só que as tools chamadas são as do servidor MCP (`mcp_client.call_tool`), com
  conversão de JSON Schema (`inputSchema` do MCP) para `types.Schema` do Gemini.
  Historico da sessao é truncado para as ultimas 8 trocas (FIFO).
- `mcp_client.py` — cliente JSON-RPC fino para `functions/mcp_server.py`, com retry
  automático de token expirado (401 → força renovação → repete a chamada uma vez).
- `auth.py` / `login.py` — Firebase ID Token via refresh token no keyring do SO
  (nunca em arquivo texto); `login.py` é um script de autenticação única
  (email/senha → refresh token, senha descartada da memória imediatamente).
- `static/index.html` + `app.js` + `style.css` — UI: forma de onda em canvas
  (alimentada tanto pelo nível do microfone quanto pelo nível do áudio de resposta
  tocando), chat com bolhas usuário/assistente, campo de texto e botão de
  push-to-talk (mousedown/touchstart para segurar).

### Decisões de escopo

- **Push-to-talk, não VAD contínuo** — segurar o botão para falar. VAD/barge-in fica
  para a fase 3 (como já estava planejado no Módulo A).
- **GEMINI_API_KEY própria e local** — não passa pelo backend do Hermes
  (`system/api_keys` no Firestore), para não exigir mais uma chamada autenticada só
  para buscar a chave. É a chave pessoal do usuário, fica só no `.env` local.
- **Cancelamento de eco pelo navegador** (`getUserMedia({echoCancellation:true})`) em
  vez de WebRTC APM manual — decisão já registrada na fase anterior da proposta.
- **Captura via `ScriptProcessorNode`** (não `AudioWorklet`) — API depreciada mas
  universalmente suportada, simples de embutir inline sem um arquivo de worklet
  separado; troca por `AudioWorklet` é um upgrade futuro de baixo risco se
  necessário.

### Verificação feita nesta fase (e o que não pôde ser verificado)

Sem GPU, sem credenciais reais (Firebase/Gemini/MCP deployado) e sem microfone/
alto-falante físicos neste ambiente de implementação, a verificação foi feita por
camadas, cada uma isolando a variável relevante:

1. **Sintaxe e imports**: todos os módulos Python compilam e importam corretamente
   (incluindo `main.py`/FastAPI com a rota `/ws` registrada) com as dependências reais
   instaladas (`pip install -r requirements.txt`, sem mocks).
2. **`orchestrator.py`**: testada a conversão de JSON Schema → `types.Schema` do
   Gemini (tipos, `required`, aninhamento) e a montagem do `types.Tool` a partir de um
   `tools/list` simulado.
3. **`mcp_client.py`**: testado com HTTP mockado — formato da requisição JSON-RPC,
   parsing de `tools/call`/`tools/list`, propagação de `McpError`, e o fluxo de retry
   em 401 (**um bug real foi encontrado e corrigido aqui**: o retry chamava
   `auth.get_id_token(force_refresh=True)` e descartava o retorno, contando com efeito
   colateral de cache em `auth.py` em vez de usar o token renovado diretamente — agora
   `_call` usa o token devolvido pela chamada com `force_refresh` sem depender de
   estado implícito entre módulos).
4. **Ponta a ponta via navegador real (Playwright + Chromium, microfone sintético
   via `--use-fake-device-for-media-stream`)**: a UI carrega sem erros de console
   relevantes, o WebSocket conecta, uma mensagem de texto digitada é enviada e uma
   bolha de erro aparece corretamente quando uma dependência falha (prova que o
   caminho de erro chega até a UI), e o push-to-talk captura áudio real do
   dispositivo sintético e envia os frames binários pelo WebSocket
   (`micChunksSent: 4` em ~1,2s de captura) — ou seja, `getUserMedia` →
   `AudioContext(16000)` → `ScriptProcessorNode` → conversão para Int16 → envio
   binário funciona de ponta a ponta no navegador.
5. **Backend via `Starlette TestClient`** (mesmo app ASGI, sem rede real): o fluxo
   completo `mic_start` → áudio binário → `mic_stop` → status "Transcrevendo..." →
   falha controlada da inicialização do faster-whisper → mensagem de erro JSON
   entregue ao cliente — funcionou corretamente na primeira tentativa.
6. **Não verificado nesta fase** (bloqueado por limitações do ambiente, não por
   decisão de escopo): download real do modelo Whisper/voz Piper (o ambiente de
   implementação bloqueia `huggingface.co` no proxy de saída — confirmado como
   `403 Forbidden`, reproduzido de forma isolada e determinística); chamada real ao
   Gemini API; chamada real ao servidor MCP deployado; login real via Firebase Auth
   REST; qualidade audível do TTS Piper; e o critério de latência "< 4s" fim a fim.
   Interessante notar: ao rodar via `uvicorn` real (em vez do `TestClient`), a mesma
   falha de rede do Whisper que retornava em segundos em chamadas isoladas passou a
   nunca completar dentro da janela observada (~30s) — não foi possível confirmar se
   é backoff/retry mais agressivo em processo "frio" ou outra particularidade do
   proxy deste ambiente; como o `TestClient` já prova a lógica da aplicação correta,
   isso foi registrado como limitação do ambiente de teste, não perseguido mais a
   fundo. Vale reconfirmar na primeira execução real na máquina do usuário.
