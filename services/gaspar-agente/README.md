# gaspar-agente — Gaspar com iniciativa (marco 1 / plano B1)

Sessão residente do Claude Code que fala com o André pelo Telegram e varre o Gaspar a cada 5 min (`/loop`).
Plano técnico: https://claude.ai/artifact/DguHwj33UzU7mh8mRx8xtw

| Arquivo | Papel |
|---|---|
| `CLAUDE.md` | persona e regras |
| `.claude/loop.md` | pulso (fila de atenção, WhatsApp, pedidos do agente) |
| `.claude/settings.json` | permissões, plugins desta pasta (telegram, fakechat; os do perfil desligados), exclui o CLAUDE.md global |
| `.mcp.json` | MCP do Gaspar pela URL direta da function (timeout 300 s) |

Diferenças em relação ao plano: tudo fica nesta pasta (escopo de projeto), não em `~/.claude`, para não mudar as outras sessões do André.
Gmail e Calendar vêm herdados dos conectores da conta (`claude_ai_Gmail`, `claude_ai_Google_Calendar`), então o 4.7 não precisa de `mcp add`.
O conector `claude_ai_Sistema_Hermes` (o Gaspar pelo Hosting) é negado para não duplicar as ~100 tools.

## Já feito
- 4.1: Bun 1.4.4, Claude Code e Git instalados (abra um terminal novo para o `bun` entrar no PATH).
- Plugins `telegram` e `fakechat` instalados com escopo de projeto.

## Passos do André (interativos)
Todos em PowerShell, dentro desta pasta.

1. **4.3 fakechat.** `claude --channels plugin:fakechat@claude-plugins-official` → responder "Yes, I trust this folder" → abrir http://localhost:8787, mandar "o que tem nesta pasta?" e ver a resposta. Se falhar, parar e rodar com `--debug`.
2. **4.4 bot.** No Telegram, @BotFather → `/newbot` → copiar o token.
3. **4.5 pareamento.** `claude`, depois `/telegram:configure <token>` e `/exit`. Rodar `claude --channels plugin:telegram@claude-plugins-official`, mandar qualquer mensagem ao bot, e no terminal `/telegram:access pair <código>` e `/telegram:access policy allowlist`.
4. **4.6 Gaspar.** Na mesma sessão, `/mcp` → `gaspar` → autenticar (login Google). Conferir `connected` e as tools `obter_estado_atual`, `obter_fila_atencao`, `consultar_pedidos_agente`.
5. Conferir no `/mcp` os nomes reais das tools e ajustar `.claude/settings.json` se algum diferir.

## Rodar (marco 1)
```powershell
claude --channels plugin:telegram@claude-plugins-official "Bom dia. Voce acabou de iniciar. 1) Chame obter_estado_atual e obter_fila_atencao. 2) Rode /loop 5m com o conteudo de .claude/loop.md. 3) Se ja passou das 07:00 e nao e janela protegida, mande ao Andre pelo telegram um bom-dia curto com no maximo 3 pontos; senao, espere a janela acabar."
```
Agendador, `encerrar.ps1` e watchdog ficam para o marco 3; o canal `gaspar-eventos`, para o marco 2.
