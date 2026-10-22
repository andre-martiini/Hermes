# gaspar-agente — Gaspar com iniciativa (marco 1 / plano B1)

Sessão residente do Claude Code que fala com o André pelo Telegram e varre o Gaspar a cada 5 min (`/loop`).
Plano técnico: https://claude.ai/artifact/DguHwj33UzU7mh8mRx8xtw

| Arquivo | Papel |
|---|---|
| `CLAUDE.md` | persona e regras |
| `.claude/loop.md` | pulso (fila de atenção, WhatsApp, pedidos do agente) |
| `.claude/settings.json` | permissões, plugins desta pasta (telegram, fakechat; os do perfil desligados), exclui o CLAUDE.md global |

Diferenças em relação ao plano: tudo fica nesta pasta (escopo de projeto), não em `~/.claude`, para não mudar as outras sessões do André.
Gmail e Calendar vêm herdados dos conectores da conta (`claude_ai_Gmail`, `claude_ai_Google_Calendar`), então o 4.7 não precisa de `mcp add`.
O Gaspar também vem do conector da conta (`claude_ai_Sistema_Hermes`, URL do Hosting). A URL direta da function não serve: o OAuth anuncia
`resource` = `gestao-hermes.firebaseapp.com/mcp` (`functions/mcp_oauth.py`) e o Claude Code recusa o login quando difere da URL cadastrada.

## Já feito
- 4.1: Bun 1.4.4, Claude Code e Git instalados (abra um terminal novo para o `bun` entrar no PATH).
- Plugins `telegram` e `fakechat` instalados com escopo de projeto.

## Passos do André (interativos)
Todos em PowerShell, dentro desta pasta.

1. **4.3 fakechat.** `claude --channels plugin:fakechat@claude-plugins-official` → responder "Yes, I trust this folder" → abrir http://localhost:8787, mandar "o que tem nesta pasta?" e ver a resposta. Se falhar, parar e rodar com `--debug`.
2. **4.4 bot.** No Telegram, @BotFather → `/newbot` → copiar o token.
3. **4.5 pareamento.** `claude`, depois `/telegram:configure <token>` e `/exit`. Rodar `claude --channels plugin:telegram@claude-plugins-official`, mandar qualquer mensagem ao bot, e no terminal `/telegram:access pair <código>` e `/telegram:access policy allowlist`.
4. **4.6 Gaspar.** Nada a autenticar: conferir em `/mcp` que `claude.ai Sistema Hermes` está `connected`.
5. Conferir no `/mcp` os nomes reais das tools e ajustar `.claude/settings.json` se algum diferir.

## Rodar (marco 1)
```powershell
.\iniciar.ps1
```
O token e o `access.json` ficam em `~/.claude/channels/telegram-gaspar` (via `TELEGRAM_STATE_DIR`), não na pasta padrão.
Motivo: o Telegram entrega cada mensagem a um único `getUpdates`. Qualquer outra sessão aberta nesta pasta (VS Code, por exemplo) sobe o plugin
e, se achasse o token, roubaria mensagens do agente. A limpeza de poller antigo do plugin usa `ps` e não funciona no Windows.
O agente não tem shell (Bash e PowerShell negados): para mudar token ou acesso, edite `.env` e `access.json` em `~/.claude/channels/telegram-gaspar`.
A hora vem da tool `agora` do canal, porque a análise de comandos de PowerShell do Claude Code às vezes estoura 5 s e trava o agente pedindo permissão.

## Marco 2: canal gaspar-eventos
`gaspar-eventos/server.ts` consulta o Firestore a cada 20 s e empurra para a sessão:
- itens abertos da fila de atenção;
- WhatsApp recebido em conversa individual (grupos e Status ficam de fora);
- promessas vencidas.

O `iniciar.ps1` liga o canal sozinho quando existe `firebase_service_account_key.json` na raiz do repositório; aí o pulso cai para 15 min.
A variável `GASPAR_EVENTOS=1` impede que outra sessão aberta na pasta suba o canal e adiante o cursor.
Na primeira subida com o canal, o Claude Code pede confirmação do `--dangerously-load-development-channels`.

Diferenças em relação ao plano:
- **Fila de atenção:** consultada só por `atualizado_em`, com o `estado` filtrado no canal, porque não há índice composto `estado`+`atualizado_em`.
- **Credencial:** a conta de serviço do worker do WhatsApp, não o login por senha do dono (a conta do André só entra com Google).
  Ela é admin e ignora as regras. O código só lê as 3 coleções, e o `settings.json` impede o agente de ler a chave
  (Read só na pasta do agente; Read, Bash e PowerShell negados para o arquivo da chave).

## Marco 3: operação sozinho
- **Perfil próprio:** o `iniciar.ps1` usa `CLAUDE_CONFIG_DIR=~/.claude-gaspar`, com login, plugins, memória e configurações separados dos do André.
  Na primeira subida, o Claude Code pede login nesse perfil e a confiança na pasta.
- **Confirmação do canal próprio:** o Claude Code pede a cada início, sem opção para lembrar. Um job no `iniciar.ps1` aperta Enter
  na janela do agente, só com a tela desbloqueada, até a sessão começar.
- **Uma instância só:** o `iniciar.ps1` sai sem fazer nada se o agente já está rodando. Por isso a mesma tarefa serve para ligar e para vigiar.
- **`encerrar.ps1`:** derruba só a árvore de processos do agente (o claude dele, o Telegram e o canal), não as outras sessões.

Agendador (como o usuário do André). Liga às 06:00 e repete a cada 30 min até 18:30 (vigia); desliga às 19:00, só em dias úteis:
```powershell
schtasks /Create /TN "Gaspar - iniciar" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 06:00 /RI 30 /DU 12:31 /IT /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\Bolsista\Repositorios\Hermes\services\gaspar-agente\iniciar.ps1" /F
schtasks /Create /TN "Gaspar - encerrar" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 19:00 /IT /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\Bolsista\Repositorios\Hermes\services\gaspar-agente\encerrar.ps1" /F
```

Energia (o André roda; no adaptador de tomada: não suspender, não hibernar, tampa fechada não faz nada):
```powershell
powercfg /change standby-timeout-ac 0; powercfg /change hibernate-timeout-ac 0; powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0; powercfg /setactive SCHEME_CURRENT
```
