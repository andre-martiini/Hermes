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
- WhatsApp recebido em conversa individual (grupos, Status e Canais ficam de fora);
- promessas vencidas;
- reações de contatos a mensagens do André em conversa individual, gravadas pelo worker em `whatsapp_reactions` (`services/whatsapp-capture/reacoes.js`). Uma reação removida não vira evento.

O `iniciar.ps1` liga o canal sozinho quando existe `firebase_service_account_key.json` na raiz do repositório; aí o pulso cai para 15 min.
A variável `GASPAR_EVENTOS=1` impede que outra sessão aberta na pasta suba o canal e adiante o cursor.
Na primeira subida com o canal, o Claude Code pede confirmação do `--dangerously-load-development-channels`.

Entrega e telemetria (revisão externa de 22/10):
- **Identidade do evento:** um item da fila de atenção é identificado pelo conteúdo (título, resumo, prioridade, prazo, pessoa, sugestão), não por `atualizado_em`. O backend regrava esse campo a cada reavaliação, de hora em hora, e o mesmo item chegava várias vezes por dia.
- **Reentrega:** evento entregue e não marcado com `marcar_visto` fica em `state/cursor.json` (`pendentes`, até 200) e volta para a sessão no próximo início. Item que fecha ou muda de versão sai dos pendentes.
- **Texto limitado:** conteúdo de WhatsApp vai cortado em 1.500 caracteres; o texto inteiro sai por `ler_mensagens_whatsapp`.
- **`consumo_hoje`:** soma os tokens do dia a partir das transcrições do perfil do agente (deduplicadas por `message.id`). O pulso grava o resultado em `contadores` de `registrar_execucao_agente`.
- **Modelo:** o agente roda no Sonnet 5.5 (`--model` no `iniciar.ps1`).

Ajustes do primeiro dia de uso (22/10):
- **Áudio do WhatsApp chega transcrito:** o canal baixa o arquivo do Storage (`media.storage_path`) e usa o mesmo Groq Whisper; o agente avalia todo áudio.
- **Grupos vigiados:** a tool `vigiar_grupo` liga e desliga grupos, e a lista persiste em `state/cursor.json`.
- **Avisos técnicos filtrados:** `e2e_notification`, `gp2` e semelhantes deixam de chegar.
- **WhatsApp com um botão só:** `schedule_whatsapp_message` sai do "ask"; o botão fica no `confirmar_acao`.
- **Apagar evento de agenda:** `delete_event` passa de proibido para "ask" (botão).
- **`github_ler` enxuto:** listas da API (PRs, issues, commits, repositórios, pastas) viram uma linha por item; um PR avulso vem com a descrição; arquivo segue em texto puro. A lista de 30 PRs do Eco caiu de 517 mil para 3,5 mil caracteres.
- **Planilhas pelo Telegram:** a tool `ler_planilha` converte xlsx, xls, ods ou csv da pasta de anexos do bot em CSV, aba por aba. Usa a SheetJS 0.20.3 do CDN oficial: a versão do npm (0.18.5) tem falhas conhecidas. Tem a mesma trava de pasta do `transcrever_audio`.
- **Drive e e-mail:** pesquisa e leitura no Google Drive liberadas; criar, alterar, copiar ou compartilhar arquivo pedem aval, e apagar é proibido. O pulso busca e-mail lido também, porque o André lê no celular antes.
- **Memória do Telegram entre reinícios:** a tool `conversa_telegram` relê as transcrições do perfil do agente (`~/.claude-gaspar/projects`) e devolve só a conversa do Telegram (mensagens do André, áudios transcritos e respostas do agente), de todas as sessões das últimas 24 h. O agente a chama ao iniciar. Não grava nada novo: usa o histórico que o Claude Code já mantém.
- **Menos turnos:** `awaySummaryEnabled` e `promptSuggestionEnabled` desligados (aqui e em `~/.claude-gaspar/settings.json`).
- **Imagem de WhatsApp:** o canal baixa a imagem do Storage (`media.storage_path`, até 10 MB) para a inbox do agente e o evento traz o caminho; o agente abre com Read e avisa o André só das importantes.
- **`CLAUDE.md`:** ciclo da sessão, agenda "Ações Gaspar", parâmetros que costumam errar e bom-dia uma vez por dia.

Diferenças em relação ao plano:
- **Fila de atenção:** consultada só por `atualizado_em`, com o `estado` filtrado no canal, porque não há índice composto `estado`+`atualizado_em`.
- **Credencial:** a conta de serviço do worker do WhatsApp, não o login por senha do dono (a conta do André só entra com Google).
  Ela é admin e ignora as regras. O código só lê as 3 coleções, e o `settings.json` impede o agente de ler a chave
  (Read só na pasta do agente; Read, Bash e PowerShell negados para o arquivo da chave).

## Marco 3: operação sozinho
- **Perfil próprio:** o `iniciar.ps1` usa `CLAUDE_CONFIG_DIR=~/.claude-gaspar`, com login, plugins, memória e configurações separados dos do André.
  Na primeira subida, o Claude Code pede login nesse perfil e a confiança na pasta.
- **Confirmação do canal próprio:** o Claude Code pede a cada início, sem opção para lembrar. Um job no `iniciar.ps1` escreve Enter direto no buffer de entrada do console do agente (`WriteConsoleInput`), sem depender de foco nem de tela desbloqueada, até a sessão começar.
- **Briefing da manhã:** todos os dias às 05:00, pelo Telegram (`.claude/briefing.md`; levantamento num subagente, para as leituras não ficarem no contexto do dia). A tarefa "Briefing da manhã do Gaspar" do app desktop foi desativada.
- **Uma instância só:** o `iniciar.ps1` sai sem fazer nada se o agente já está rodando. Por isso a mesma tarefa serve para ligar e para vigiar.
- **`encerrar.ps1`:** derruba só a árvore de processos do agente (o claude dele, o Telegram e o canal), não as outras sessões.

Agendador (como o usuário do André). O agente roda 24 h, todos os dias.
- **"iniciar":** a cada 30 min, o dia inteiro. Funciona como vigia: sai sem fazer nada se o agente já está rodando.
- **"encerrar":** às 04:30 reinicia a sessão (contexto novo); o vigia das 05:00 a religa a tempo do briefing.

Recriar com `/F` encerra a instância que está rodando: rode `schtasks /Run /TN "Gaspar - iniciar"` em seguida.
```powershell
schtasks /Create /TN "Gaspar - iniciar" /SC DAILY /ST 00:00 /RI 30 /DU 24:00 /IT /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\Bolsista\Repositorios\Hermes\services\gaspar-agente\iniciar.ps1" /F
schtasks /Create /TN "Gaspar - encerrar" /SC DAILY /ST 04:30 /IT /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\Bolsista\Repositorios\Hermes\services\gaspar-agente\encerrar.ps1" /F
```
O pulso só roda das 05:00 às 22:59 (`*/15 5-22 * * *`); de madrugada, só os eventos acordam o agente.
Depois de um reinício do Windows (ex.: Windows Update de madrugada), o agente só volta quando o André fizer login, porque a tarefa é "interativa apenas".

Energia (o André roda; no adaptador de tomada: não suspender, não hibernar, tampa fechada não faz nada):
```powershell
powercfg /change standby-timeout-ac 0; powercfg /change hibernate-timeout-ac 0; powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0; powercfg /setactive SCHEME_CURRENT
```
