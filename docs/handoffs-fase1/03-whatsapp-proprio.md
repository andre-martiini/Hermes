# PR 3 (Fase 1) — `feat(outbox): aprovacao por resposta no whatsapp proprio`

## Revisão (04/09/2026, após investigação do Dev) — leia isto primeiro, substitui parte do desenho original abaixo

Sua investigação foi ótima e mudou o desenho pra melhor — obrigado por ter parado em vez de forçar. Resumo do que você achou e o que muda:

- **Item 2 (dispatcher) confirmado 100%:** `functions/atencao_whatsapp.py::on_whatsapp_message_atencao`, trigger em `whatsapp_messages/{message_id}`. Isso não muda.
- **Item 1 (self-chat) tem 3 limitações reais**, mas nenhuma delas impede a funcionalidade — elas só invalidam o mecanismo de **preview_wa_message_id** que eu tinha proposto (que dependia do Hermes mandar uma mensagem de preview PARA o WhatsApp de forma síncrona, e isso não existe: o envio é assíncrono, via outbox + worker com cron de 60s, ou cai no fallback do Telegram com link `wa.me`). Em vez de encaixar esse mecanismo síncrono à força, **elimine o preview do desenho por completo** — não é necessário. Veja como abaixo.

### Desenho revisado (substitui as seções "Preview no self-chat" e "Novo detector" originais)

**Não crie `preview_wa_message_id` nem mande preview nenhum pro WhatsApp.** O dono já sabe que existe um rascunho pendente por outro caminho (card do Telegram, fila de atenção, briefing) — a única coisa que falta é um jeito de ele dizer "sim/não/editar" sem precisar trocar de app. Resolva por **contagem de pendentes**, não por ID de mensagem:

1. **Novo setting:** adicione `whatsapp_owner_chat_id` em `system/settings` (mesmo documento que `atencao_whatsapp.py` já lê nas linhas ~293/300 pra outras flags). É o chat_id do dono no formato `@c.us` (o `ownWid` que você identificou no bridge). Esse campo é preenchido manualmente uma vez — não é código, é dado de configuração; documente no PR como preenchê-lo (não deixe hardcoded no Python).
2. **Lógica pura nova** (mesmo padrão dos detectores existentes): `interpretar_resposta_aprovacao_whatsapp(mensagem: dict, rascunhos_pendentes: list[dict]) -> dict | None`.
   - Só considera `mensagem.get("from_me") is True` e `mensagem.get("chat_id") == whatsapp_owner_chat_id` (settings). Qualquer outro chat: `None` (ignora, sem exceção).
   - Se `rascunhos_pendentes` (a lista de `aguardando_aprovacao`) estiver vazia: `None` (é só o dono escrevendo pra ele mesmo por outro motivo).
   - Se tiver **exatamente um** pendente: interpreta o texto — "sim/ok/pode/manda" → aprovar; "nao/não/descarta/cancela" → descartar; qualquer outro texto não vazio → editar (novo texto do rascunho). Devolve `{"outbox_id": ..., "acao": "aprovar" | "descartar" | "editar", "novo_texto": ...}`.
   - Se tiver **mais de um** pendente: devolve `{"acao": "ambiguo", "quantidade": N}` — não tenta adivinhar qual. Trate a desambiguação por texto/contato como melhoria futura, fora desta PR.
3. **Hook no dispatcher** (`on_whatsapp_message_atencao`): busca pendentes com `outbox_aprovacao.listar_rascunhos(db)` (já existe, já filtra por `status == aguardando_aprovacao` — não precisa mudar nada nela) e chama a função pura acima. Se a decisão for `aprovar`/`descartar`/`editar`, chama a função correspondente de `outbox_aprovacao.py`. Se for `ambiguo`, apenas registre/logue (ou, se for barato, responda no self-chat algo como "Há {N} rascunhos pendentes — aprove pelo Telegram por enquanto."; não é obrigatório nesta PR, mas é bem-vindo se for simples).
4. Confirmação de volta ao self-chat (opcional, mesma lógica de antes: "✅ Enviando.", "🗑️ Descartado.", "✏️ Rascunho atualizado.") continua sendo um bônus, não bloqueador — se mandar mensagem de confirmação passar pelo mesmo outbox/worker assíncrono de 60s, tudo bem, não precisa ser instantâneo.

Isso elimina as 3 limitações de uma vez: não depende do worker/cron pra nada (só lê `whatsapp_owner_chat_id` de settings e a lista de rascunhos, ambos sempre disponíveis de forma síncrona no Python), não precisa do ID de uma mensagem que ainda nem foi enviada, e não toca no fluxo de envio existente.

### O que já valia no desenho original (não mudou)

- Reaproveitar `aprovar_rascunho`/`descartar_rascunho`/`aplicar_edicao_rascunho` de `outbox_aprovacao.py` sem criar nova máquina de estados — continua exatamente assim.
- Travas: só reage no self-chat do dono, nunca em chat de terceiro; nunca reintroduz validação de transição (delega tudo pra `outbox_aprovacao.py`); não muda quem aprova nem o que pode ser aprovado.
- Gate de testes: `cd functions && python -m unittest discover -s . -p "test_*.py"`.

### Testes (ajustado)

- `interpretar_resposta_aprovacao_whatsapp`: cobre aprovar/descartar/editar com 1 pendente, `None` com 0 pendentes, `ambiguo` com 2+ pendentes, e mensagem em chat de terceiro (ignora mesmo com texto parecido com comando, mesmo com pendentes existindo).
- Teste leve confirmando que o hook chama a função certa de `outbox_aprovacao.py` pra cada ação.

### Docs (ajustado)

`docs/okf/arquitetura/schema-firestore.md` (novo campo `whatsapp_owner_chat_id` em `system/settings` — **não** mais `preview_wa_message_id`, que foi descartado), `docs/okf/copiloto/mcp-servidor.md` se houver mudança de comportamento visível, `docs/okf/log.md`. Inclua no PR uma linha explicando que `whatsapp_owner_chat_id` precisa ser preenchido manualmente uma vez (qual é o valor esperado, como descobrir o `ownWid` — você já sabe, pelo que investigou no bridge).

---

## Handoff original (para contexto — partes de desenho substituídas pela Revisão acima)

**Pré-requisito:** PR #156 (outbox) mergeado. Não depende de outro PR desta fase.

### Por quê

Hoje a única forma de aprovar/descartar/editar um rascunho do outbox (`criar_rascunho_whatsapp`, PR #156) é pelo card com botões no Telegram. O dono às vezes está com o WhatsApp aberto e não com o Telegram — o critério de pronto da Fase 1 pede que ele consiga aprovar respondendo diretamente no WhatsApp, sem precisar abrir outro app.

### Travas

- O detector só reage a mensagens no self-chat do próprio dono — nunca em chat de terceiro. Resposta digitada na conversa de um contato jamais pode ser interpretada como aprovação.
- Nunca reintroduza validação de transição de estado aqui — sempre delegue para `outbox_aprovacao.py`. Se o `outbox_id` resolvido já estiver decidido, a chamada às funções existentes já devolve `already_decided` — só não quebre nesse caso.
- Esta PR não muda quem pode aprovar (continua sendo só o dono, agora por dois canais) nem o que pode ser aprovado (regra do Eixo 3 sobre outbox continua igual).
