# PR 1 (Fase 1) — `feat(agent-requests): fila de trabalho autonomo e consolidacao de audio`

**Pré-requisito:** PR #155 mergeado (detector `audio_relevante` em `functions/atencao_whatsapp.py`). Não depende de outro PR desta fase.

## Por quê

O Hermes não consegue disparar uma sessão do Cowork sozinho. O que ele pode fazer é enfileirar trabalho numa coleção que a próxima sessão agendada (o "executor", criado como rotina do Cowork depois deste PR mergear, do mesmo jeito que o briefing e a varredura de follow-ups da Fase 0) consome sozinha. O primeiro uso real: quando o detector `audio_relevante` (PR #155) já sinaliza um áudio de contato vinculado a ação ativa, hoje isso só vira consolidação de verdade se o dono notar o item na fila e pedir ao Claude para consolidar. Este PR fecha esse loop sem o dono precisar notar nada.

## Desenho — o mínimo que funciona

### Coleção `agent_requests`

Documento por pedido de trabalho autônomo:

```
{
  tipo: "consolidar_audio",              # string; único tipo implementado nesta PR
  status: "pendente" | "em_andamento" | "concluido" | "erro",
  payload: { ... },                       # formato depende do tipo
  origem: "atencao_whatsapp.audio_relevante",
  item_atencao_id: "abc123" | null,       # item da fila de atencao vinculado, se houver
  acao_id: "def456" | null,
  criado_em: <server timestamp>,
  atualizado_em: <server timestamp>,
  processado_em: <server timestamp> | null,
  resultado: "texto livre" | null,
  erro: "texto livre" | null,
}
```

Para `tipo: "consolidar_audio"`, `payload` é `{chat_id, chat_name, mensagem_ids: [...], acao_id, item_atencao_id}` — os mesmos dados que `consolidar_whatsapp` já espera (`message_ids`) mais o necessário para fechar o loop depois.

### Novo módulo `functions/agent_requests.py`

Mesmo padrão de separação pura/IO que `atencao.py` e `outbox_aprovacao.py` já estabelecem.

Lógica pura:
- `validar_transicao(status_atual: str | None) -> tuple[bool, str]`: só aceita concluir/errar a partir de `pendente` ou `em_andamento`; `concluido` e `erro` são terminais (não regridem, não se sobrescrevem — toque duplo do executor não duplica trabalho nem apaga o resultado já gravado).
- `montar_payload_consolidar_audio(chat_id, chat_name, mensagem_ids, acao_id, item_atencao_id) -> dict`.

Operações (recebem `db`):
- `enfileirar_ou_atualizar(db, doc_id, tipo, payload, origem, acao_id=None, item_atencao_id=None) -> dict`: `set(merge=True)` no doc `agent_requests/{doc_id}` com `status: "pendente"` se o doc não existe ou ainda está `pendente`; se já está `em_andamento`, `concluido` ou `erro`, **não mexe** (o pedido já foi pego ou fechado — sobrescrever o payload de um pedido em andamento criaria uma corrida com o executor). `doc_id` é escolhido por quem chama, não gerado aqui — ver abaixo por quê.
- `listar_pendentes(db, tipo: str | None = None, limite: int = 20) -> dict`: `status == "pendente"`, filtra por `tipo` se informado, ordena por `criado_em` crescente (mais antigo primeiro).
- `concluir(db, request_id: str, resultado: str | None = None, erro: str | None = None) -> dict`: exige exatamente um de `resultado`/`erro`; valida transição; grava `status: concluido` (se `resultado`) ou `status: erro` (se `erro`), `processado_em`. Idempotente: se já terminal, devolve `{"status": "already_decided", "estado_atual": ...}` sem sobrescrever — mesmo padrão de `aprovar_rascunho` (PR #156).

### Hook no detector de áudio (`functions/atencao_whatsapp.py`)

No ponto em que `_processar_audio` (ou equivalente — confira o nome exato no arquivo, foi implementado no PR #155) grava/mescla o item de atenção `audio_relevante`, adicione a chamada a `agent_requests.enfileirar_ou_atualizar`.

**`doc_id` determinístico e igual à chave de mesclagem do item de atenção** (mesma ideia de `chave_dedupe` que os detectores já usam): use o `item_atencao_id` do item de atenção correspondente como base do `doc_id` do `agent_request` (ex.: `f"consolidar_audio:{item_atencao_id}"`). Isso resolve de graça o caso de sequência de áudios: quando um segundo áudio chega dentro da janela de 10 min e é mesclado ao mesmo item de atenção (`mesclar_ou_criar_item_audio`, já existente), o hook roda de novo com o mesmo `item_atencao_id` → mesmo `doc_id` → `enfileirar_ou_atualizar` faz merge do payload (lista de `mensagem_ids` atualizada) em vez de criar um segundo pedido. Se o pedido já estiver `em_andamento` ou `concluido` quando o segundo áudio chegar (executor rodou entre um áudio e outro), não mexe — o próximo áudio (fora da janela de 10 min, vira item novo de atenção) gera um `agent_request` novo, com seu próprio `item_atencao_id`.

### Tools MCP novas

- **`consultar_pedidos_agente`** (leitura): args `tipo` (opcional), `limite` (padrão 20, máx. 50). Chama `listar_pendentes`. Devolve os pedidos pendentes para a sessão executora decidir o que fazer.
- **`concluir_pedido_agente`** (escrita, **sem** exigir confirmação — é o próprio agente fechando seu próprio trabalho autônomo, sem efeito em terceiro, mesma categoria de `registrar_no_diario`): args `request_id`, e exatamente um de `resultado`/`erro`. Chama `concluir`. Registre no catálogo/schema/handler como sempre; **não** entra em `registry._NEEDS_CONFIRMATION` (não grava efeito externo, só fecha um pedido interno) nem em `mcp_server._CONFIRMACAO_OBRIGATORIA`.

Nenhuma tool para *criar* um `agent_request` é exposta ao Claude nesta PR — quem enfileira é código Python (o hook do detector), não o modelo. Isso evita o LLM inventar `tipo` que o executor não sabe tratar. Se uma sessão de conversa precisar enfileirar trabalho para depois, isso é decisão de PR futuro, não deste.

### `obter_estado_atual`

Adicione a chave `agent_requests_pendentes` com a **contagem** de pedidos pendentes (não a lista — a lista completa é para quem vai executar, via `consultar_pedidos_agente`; o estado geral só precisa saber que há trabalho autônomo esperando).

## Travas

- `agent_requests` nunca é caminho para efeito em terceiro. Nenhum tipo implementado nesta PR (ou em PR futuro) pode terminar em mensagem/e-mail enviado direto — o resultado de um pedido autônomo que envolva contato com alguém é sempre um rascunho no outbox.
- `concluir_pedido_agente` não aceita mudar `status` para nada além de `concluido`/`erro`, e nunca reabre um pedido já terminal.
- O enfileiramento é sempre por código (hook), nunca por tool MCP — ver acima.

## Testes

- `functions/test_agent_requests.py` (novo): transições válidas/inválidas; `concluir` idempotente (toque duplo não sobrescreve); `enfileirar_ou_atualizar` faz merge de payload quando pendente e não mexe quando já `em_andamento`/terminal.
- `functions/test_atencao_whatsapp.py`: novo teste garantindo que o hook cria o `agent_request` com o `doc_id` esperado na primeira mensagem de áudio, e que uma segunda mensagem na janela de 10 min atualiza o mesmo doc (lista de `mensagem_ids` crescendo) em vez de criar outro.
- `functions/test_hermes_tools.py`: cobertura automática de catálogo ↔ schema ↔ handler das duas tools novas (o teste existente já pega isso).

Gate completo: `cd functions && python -m unittest discover -s . -p "test_*.py"`.

## Fora de escopo

O que o executor faz com `tipo: "consolidar_audio"` **não é código Python desta PR** — é a rotina agendada do Cowork ("executor a cada 2h"), criada depois deste PR mergear, chamando `consultar_pedidos_agente` → `consolidar_whatsapp` (já existe) → `registrar_no_diario` (já existe) → `resolver_item_atencao` (já existe, PR #154) → `concluir_pedido_agente` (desta PR), tudo via MCP, sem precisar de nenhuma tool nova para orquestrar isso. Outros tipos de `agent_request` (ex.: o que viria a alimentar `contexto_agente`) são PRs futuros desta fase.

## Docs

`docs/okf/arquitetura/schema-firestore.md` (nova coleção `agent_requests`), `docs/okf/arquitetura/cloud-functions.md` (menção ao hook em `atencao_whatsapp.py`), `docs/okf/copiloto/mcp-servidor.md` (as duas tools novas), `docs/okf/log.md`.
