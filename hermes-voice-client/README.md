# Hermes Voice Client (fase 2 — cliente local)

Cliente de voz local do copiloto Hermes: uma UI web servida em `localhost`
com forma de onda ao vivo e chat (voz ou texto), rodando STT/TTS na sua
máquina (GPU, se disponível) e usando o [servidor MCP do Hermes](../functions/mcp_server.py)
para acessar dados reais (tarefas, acervo, contatos, calculadora).

Ver a proposta completa em
`../docs/okf/copiloto/proposta-interface-vocal-mcp.md`.

## Como funciona

```
navegador (forma de onda + chat)
   │ WebSocket (áudio PCM16 16kHz + texto/controle)
   ▼
main.py (FastAPI, local)
   │
   ├─ stt.py       → faster-whisper (transcreve a fala)
   ├─ orchestrator.py → Gemini (gemini-3.1-flash-lite) com as tools do MCP
   │                    como function declarations
   ├─ mcp_client.py → chama o servidor MCP do Hermes (tools/list, tools/call,
   │                   resources/read) autenticado por Firebase ID Token
   └─ tts.py        → Piper (sintetiza a resposta, frase a frase)
```

Escopo desta fase: **push-to-talk** (segurar o botão do microfone para
falar). VAD contínuo, barge-in e cancelamento de eco além do nativo do
navegador ficam para a fase 3.

## Pré-requisitos

1. **Servidor MCP do Hermes já deployado** (fase 1,
   `functions/mcp_server.py`) e com o seu UID liberado em
   `system/mcp_access.allowed_uids` no Firestore — sem isso o cliente local
   autentica mas o MCP recusa as chamadas.
2. Python 3.11+.
3. GPU opcional (recomendada): acelera faster-whisper. Sem GPU, funciona em
   CPU com `WHISPER_COMPUTE_TYPE=int8`, só que mais devagar.
4. Chave própria do Gemini API (`GEMINI_API_KEY`) — fica local, não passa
   pelo backend do Hermes.

## Setup

```bash
cd hermes-voice-client
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edite .env: FIREBASE_WEB_API_KEY, HERMES_MCP_URL, GEMINI_API_KEY

python login.py             # login único, guarda o refresh token no keyring do SO
```

Na primeira execução, `stt.py` baixa o modelo Whisper configurado
(`WHISPER_MODEL`, padrão `large-v3-turbo`, ~1.5GB) e `tts.py` baixa a voz
Piper configurada (`PIPER_VOICE`, padrão `pt_BR-faber-medium`, algumas
dezenas de MB) — precisa de internet nessa primeira vez. Se a conexão for
limitada, troque `WHISPER_MODEL=small` no `.env` para um download menor.

## Rodar

```bash
uvicorn main:app --port 8765
```

Abra `http://localhost:8765` no navegador. Segure o botão do microfone para
falar (solta para enviar) ou digite no campo de texto — os dois caminhos
passam pelo mesmo copiloto, com as mesmas ferramentas do Hermes.

## Limitações conhecidas desta fase

- Só as tools marcadas como `voice_enabled` no servidor MCP funcionam aqui
  (hoje: `consultar_historico_acoes`, `buscar_arquivos_acervo`,
  `buscar_contato`, `calculadora`) — as demais ainda não têm executor ligado
  ao MCP (ver `functions/tools/mcp_dispatch.py`).
- Sem VAD/barge-in: é preciso segurar o botão para falar.
- Qualidade da voz Piper em pt-BR não foi validada por escuta ainda — troque
  `PIPER_VOICE` e compare se o resultado não agradar.
- Memória de conversa é só da sessão atual (mantida em RAM enquanto o
  servidor local roda); reiniciar `uvicorn` zera o histórico.
