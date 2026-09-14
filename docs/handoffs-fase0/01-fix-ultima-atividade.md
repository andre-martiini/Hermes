# PR 1 — `fix(whatsapp): last_activity_ts atualizado a cada mensagem capturada`

## Problema observado (03/09/2026)

`listar_conversas_whatsapp` devolveu `ultima_atividade` de 23:06 do dia anterior para conversas que tinham mensagens novas às 14h do dia corrente. O agente que consome a lista para triagem ordena por esse campo e decide o que ler — com o campo defasado, conversas quentes caem para o fim da lista ou ficam fora do `limite`.

## Causa raiz

`ultima_atividade` vem de `whatsapp_chats/{chatId}.last_activity_ts` (`functions/tools/whatsapp_tools.py`, linha ~158). Esse campo só é escrito pela **sincronização do registro de chats** em `services/whatsapp-capture/index.js` (função que chama `client.getChats()`, por volta da linha 240), que roda a cada **6 horas** (`CHATS_SYNC_INTERVAL_MS`, linha ~55). A captura de mensagens ao vivo (`handleMessage`, gravação em `whatsapp_messages` por volta da linha 507) **não** toca o documento do chat.

## O que fazer

Em `services/whatsapp-capture/index.js`, logo após a gravação bem-sucedida da mensagem em `whatsapp_messages` (o `set(msgData, { merge: true })` na função que grava — linha ~507), atualizar o documento do chat:

```js
await db.collection('whatsapp_chats').doc(chatId).set({
    chat_id: chatId,
    last_activity_ts: msgData.timestamp,
}, { merge: true });
```

Condições:

- Só avance o carimbo: se o documento já tiver `last_activity_ts` **maior** que `msgData.timestamp` (acontece no backfill de mensagens antigas — ver a função que completa histórico por volta da linha 612), não regrida. Uma leitura antes do `set` custa uma ida ao Firestore por mensagem; alternativa aceitável é manter um `Map` em memória `chatId → último ts gravado` e só escrever quando o novo for maior. Prefira o `Map` — o worker é processo único.
- Não bloqueie a gravação da mensagem por falha aqui: envolva em `try/catch` com `console.warn`, no mesmo espírito do `[Chats]` que já existe.
- Não altere a sincronização de 6h — ela continua sendo quem descobre chats novos e resolve `contact_number`.

Não é necessário mudar nada em Python: `listar_conversas` já lê o campo certo.

## Teste

O worker não tem suíte automatizada. Valide manualmente:

1. Rode o worker localmente (`services/whatsapp-capture`, ver `run-hidden.bat`/`start-hidden.vbs` para o comando) ou reinicie o que está em produção.
2. Envie uma mensagem para si mesmo ou peça uma mensagem numa conversa monitorada.
3. Em até alguns segundos, `listar_conversas_whatsapp` (via MCP) ou o Console do Firestore deve mostrar `last_activity_ts` igual ao `timestamp` da mensagem.
4. Confira que uma mensagem antiga reprocessada pelo backfill **não** regride o carimbo.

Documente o resultado desses passos na descrição do PR.

## Fora de escopo

Não recalcular `ultima_atividade` a partir de `whatsapp_messages` no lado Python — resolveria o sintoma com uma query por chat a cada listagem; o problema é do lado da escrita.

## Docs

Adicionar uma linha em `docs/okf/integracoes/whatsapp.md` dizendo que `last_activity_ts` é mantido pela captura ao vivo e pela sincronização de 6h, e registrar em `docs/okf/log.md`.
