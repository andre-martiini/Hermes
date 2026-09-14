# PR 4 — `feat(outbox): rascunhos com aprovacao em um toque pelo Telegram`

**Pré-requisito:** PR 2 mergeado (para vincular rascunho a item da fila). Não depende do PR 3.

## Por quê

Hoje toda mensagem a terceiro passa por conversa: o Claude redige, o dono lê, autoriza, o Claude chama `schedule_whatsapp_message` com a dupla confirmação. Em 03/09/2026 essa chamada final foi bloqueada por política do cliente e o dono teve que copiar e colar a mensagem no WhatsApp à mão. O objetivo é que **redigir** e **aprovar** sejam coisas separadas: o agente deixa o rascunho pronto; o dono aprova com um toque onde estiver; o worker envia.

## Desenho — o mínimo que funciona

A coleção `whatsapp_outbox` **já existe** e o worker (`services/whatsapp-capture/index.js`, ~linha 929) só envia documentos com `status == "pending"`. Um novo status `aguardando_aprovacao` fica, por construção, fora do envio. Aprovar é trocar para `pending`. Nada muda no worker.

### Tool `criar_rascunho_whatsapp` (escrita — `_NEEDS_CONFIRMATION`)

Args: `contact_number` (número com DDI/DDD **ou** `chat_id` `@g.us`/`@lid`, como `schedule_whatsapp_message` aceita), `message`, `motivo` (uma frase: por que este rascunho existe), `acao_id` (opcional), `item_atencao_id` (opcional).

Grava em `whatsapp_outbox/{id}` com os mesmos campos que `schedule_whatsapp_message.py` usa (`to_number`, `content`, `created_at`) mais: `status: "aguardando_aprovacao"`, `motivo`, `acao_id`, `item_atencao_id`, `origem: "claude"` (ou o `session_id` do `ToolContext`), `destinatario_nome` (resolvido por `whatsapp_chats.chat_name`/`contact_number` — reuse a resolução que `schedule_whatsapp_message` já faz para o preview, sem duplicar). **Não** grava `scheduled_for`: quem aprova define quando sai (imediato).

Resolução de destinatário: exatamente a mesma que `schedule_whatsapp_message` usa hoje, inclusive as validações adicionadas em 02/09 (`fix: validar destinatário no gate MCP`, `fix: proteger confirmação de destinatário e outbox`). Se a resolução for parcial ou ambígua, **recuse** o rascunho com a lista de candidatos — nunca deixe um rascunho com destinatário incerto na fila.

Depois de gravar, enviar ao Telegram do dono (mesmo `chat_id` whitelisted que os demais avisos usam) uma mensagem:

```
✉️ Rascunho para {destinatario_nome}
{motivo}

"{content}"

[✅ Enviar] [✏️ Editar] [🗑️ Descartar]
```

Botões inline com `callback_data`: `outbox:{id}:ok`, `outbox:{id}:edit`, `outbox:{id}:no`. Guarde o `message_id` do Telegram no doc (`telegram_message_id`) para editar a mensagem depois da decisão, como `ai_notif:` faz.

Devolve `{status: "aguardando_aprovacao", outbox_id, destinatario_nome}` e a instrução textual: "O rascunho foi para aprovação do dono no Telegram. Não afirme que a mensagem foi enviada; use consultar_envio_whatsapp com este id para saber o estado real."

### Callback no Telegram (`functions/hermes_core_logic.py::_handle_telegram_callback`)

Novo ramo `elif data.startswith("outbox:")`, ao lado de `emlink:` (~linha 2858) e `ai_notif:` (~linha 2399). Mesma estrutura desses dois — leia-os antes.

- `ok`: transição **atômica** `aguardando_aprovacao → pending` (transação Firestore; se o status já não for `aguardando_aprovacao`, responda "já decidido" e não faça nada — protege contra toque duplo). Grava `aprovado_em`, `aprovado_via: "telegram"`. Edita a mensagem do Telegram para "✅ Enviado para a fila às HH:MM". Se houver `item_atencao_id`, marca o item como `resolvido` com `desfecho="mensagem aprovada e enviada"`. Se houver `acao_id`, registra no diário da ação (mesma função de `registrar_no_diario`).
- `no`: `status: "descartado"`, `descartado_em`. Edita a mensagem para "🗑️ Descartado". Item da fila, se houver, volta para `aberto` (o dono descartou o texto, não o assunto).
- `edit`: responde no Telegram "Me manda o texto novo em resposta a esta mensagem" e **trava a sessão** do Telegram para capturar a próxima mensagem como novo `content` — reuse o mecanismo que `diary_edit:` já usa para capturar o ajuste do diário. A mensagem capturada substitui `content`, o rascunho volta a `aguardando_aprovacao` e o card é reenviado com os três botões. O texto editado pelo dono é a fonte da verdade: não passe por LLM.

### `consultar_envio_whatsapp`

Já lê `whatsapp_outbox`. Garanta que reconhece `aguardando_aprovacao` e `descartado` e os descreve corretamente (hoje distingue `pending` na fila de `pending` encalhado — adicione "aguardando aprovação do dono no Telegram" e "descartado pelo dono"). Ajuste `functions/test_whatsapp_tools.py`.

### `listar_rascunhos_pendentes` (leitura)

Tool pequena: lista `whatsapp_outbox` com `status == "aguardando_aprovacao"`, para o Claude conferir o que ainda espera decisão e não redigir de novo o mesmo rascunho. Args: `limite` (padrão 20).

## Travas

- **Nenhum caminho leva de `aguardando_aprovacao` a `pending` sem callback do Telegram autenticado** (whitelist de `chat_id` já existente). Nem tool MCP, nem callable web — nesta versão a aprovação é só pelo Telegram. Se o dono quiser aprovar pela web ou pelo WhatsApp próprio, é outro PR.
- `schedule_whatsapp_message` continua exatamente como está, com a dupla confirmação. Este PR **adiciona** um caminho; não afrouxa o existente.
- Rascunho expira: cron diário (pode viver em `check_and_send_reminders`, que já roda a cada minuto — mas só verifique expiração uma vez por hora para não custar leitura à toa) marca `aguardando_aprovacao` com mais de 48h como `expirado` e edita o card no Telegram. Uma mensagem aprovada dois dias depois do contexto raramente ainda é a mensagem certa.

## Testes

- `functions/test_outbox_aprovacao.py` (novo): transição `ok` só de `aguardando_aprovacao`; toque duplo não duplica; `no` reabre item da fila; `edit` substitui `content` sem alterar destinatário; expiração só atinge o status certo.
- `functions/test_hermes_tools.py` (catálogo ↔ schema ↔ handler das duas tools novas).
- `functions/test_whatsapp_tools.py` (novos status em `consultar_envio_whatsapp`).
- Manual, documentado no PR: criar rascunho via MCP → card chega no Telegram → Enviar → worker envia → `consultar_envio_whatsapp` devolve `sent`. Repetir com Descartar e com Editar.

Gate completo: `cd functions && python -m unittest discover -s . -p "test_*.py"`.

## Fora de escopo

Aprovação pela web ou pelo WhatsApp do próprio dono; rascunhos de e-mail (já existe `criar_rascunho_email`, que grava no Gmail e nunca envia — modelo diferente, não misturar); envio agendado a partir de rascunho aprovado.

## Docs

`docs/okf/integracoes/whatsapp.md` (ciclo de vida do `whatsapp_outbox` com os status novos, diagrama de estados em texto), `docs/okf/copiloto/mcp-servidor.md` (as duas tools e a nota de que `criar_rascunho_whatsapp` **não** exige `_confirmed` porque não envia nada), `cloud-functions.md` (ramo `outbox:` do callback), `log.md`.
