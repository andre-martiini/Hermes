# PR 2 da Fase 3 — Promoção de autonomia por tipo de rascunho WhatsApp

Consome a fundação do PR 1 (`tipo`, `foi_editado`, `metricas_por_tipo`) para deixar
o Hermes propor, sozinho, quando um tipo de rascunho já amadureceu o suficiente
para não precisar de aprovação prévia. Contexto completo da leitura do código em
`00-visao-geral.md`.

## Restrição de design — resolvida com o André, não é opcional

O desenho original (`00-visao-geral.md`) previa pular a aprovação do Telegram
inteiramente para tipos promovidos. Ao implementar, achei um conflito com um
princípio já fixado em `mcp_server.py` (`_CONFIRMACAO_OBRIGATORIA`, condição do
dono de 02/09/2026): envio de WhatsApp é "o único efeito que não dá para desfazer
de dentro do Hermes" e por isso nunca fica sem humano no circuito, nem por
configuração. Esse comentário é sobre outro mecanismo (o gate `_confirmed=true`
do canal MCP), mas o princípio se aplica igual aqui — bypass total criaria um
terceiro caminho de envio de WhatsApp sem toque humano nenhum.

Levei para o André. Decisão: **não pular a aprovação — notificar com janela de
cancelamento.** Para tipos promovidos, o rascunho não fica esperando um "sim"
antes de entrar na fila; ele já sai anunciado no Telegram com um prazo (padrão
10 min) e um botão "Cancelar". Se ninguém cancelar, um job libera o envio
automaticamente ao fim da janela. O dono continua com poder de veto e o efeito
continua desfazível dentro do Hermes durante a janela — só inverte o padrão
(opt-out em vez de opt-in) para os tipos que já provaram, com dado real via
`metricas_por_tipo`, que raramente precisam de edição. Esse é o design abaixo.

## O que muda em `functions/outbox_aprovacao.py`

**1. Novo status `STATUS_AGUARDANDO_JANELA = "aguardando_janela"`.** Estado
intermediário só para rascunhos de tipo promovido: já tem card no Telegram, já
tem prazo de auto-liberação, mas ainda pode ser cancelado. Não reaproveitar
`STATUS_AGUARDANDO` para isso — o card, os botões e o texto são diferentes, e
misturar os dois no mesmo status obrigaria a checar campo extra em todo lugar
que hoje só olha `status`.

**2. Novo campo `envio_liberado_em` (timestamp).** Gravado só em rascunhos
`aguardando_janela`: `agora + janela_minutos`. Fonte da janela, em ordem de
prioridade: `system/mcp_access.janela_cancelamento_min` (configurável sem
deploy, mesmo doc que já guarda `allowed_uids`/`confirm_tools`) → env
`PROMOCAO_JANELA_MIN` → padrão `10`.

**3. `criar_rascunho` ganha um branch no início.** Antes de montar o payload,
ler `tipos_promovidos` de `system/mcp_access` (nova função `_tipos_promovidos(db)
-> set[str]`, leitura direta — sem cache próprio; `criar_rascunho` não é
hot-path como o gate do MCP, não precisa de TTL). Se `tipo_limpo` estiver no
conjunto:
   - `status` inicial = `STATUS_AGUARDANDO_JANELA`, grava `envio_liberado_em`.
   - Card do Telegram vem de uma função nova, `montar_card_telegram_promovido`
     (não reaproveitar `montar_card_telegram` — botões e texto diferentes; ver
     item 4). Só o botão `🛑 Cancelar` (`callback_data=f"outbox:{outbox_id}:no"`
     — **mesmo `callback_data` do fluxo atual**, propositalmente: o handler em
     `hermes_core_logic.py` linha ~2989 já resolve `outbox:{id}:no` chamando
     `descartar_rascunho`, então cancelar um rascunho promovido não precisa de
     nenhuma rota nova).
   - `instrucao` no retorno muda para deixar claro ao Claude que não é
     "aguardando aprovação": algo como "Tipo promovido — vai para a fila
     automaticamente em até {janela} min salvo cancelamento do dono. Não afirme
     que foi enviado; consulte consultar_envio_whatsapp."
   Caso contrário, fluxo idêntico ao que já existe hoje (`STATUS_AGUARDANDO`).

**4. Nova função pura `montar_card_telegram_promovido(destinatario_nome, motivo,
content, outbox_id, minutos_janela) -> tuple[str, list[list[dict]]]`.** Mesmo
formato de retorno de `montar_card_telegram`, texto deixando explícito que é
autônomo e vai sair sozinho ("🤖 Enviado automaticamente em até {minutos_janela}
min — toque para cancelar"), um único botão `Cancelar`.

**5. `validar_transicao_aprovacao` e `validar_transicao_descarte` passam a
aceitar `STATUS_AGUARDANDO_JANELA` como estado "ainda não decidido"** (hoje só
aceitam `STATUS_AGUARDANDO`). É o que permite reaproveitar `aprovar_rascunho` e
`descartar_rascunho` como estão, sem duplicar a lógica transacional, tanto para
a liberação automática quanto para o cancelamento manual.

**6. Nova função pura `avaliar_liberacao_promovidos(rascunhos, agora) ->
list[str]`.** Mesmo padrão de `avaliar_expirados`: filtra rascunhos com
`status == STATUS_AGUARDANDO_JANELA` e `envio_liberado_em <= agora`, devolve os
ids prontos para liberar.

**7. Nova função `liberar_rascunhos_promovidos(db, agora=None) -> int`.**
Espelha `expirar_rascunhos_pendentes` na estrutura (query, filtro puro, loop):
para cada id de `avaliar_liberacao_promovidos`, chama `aprovar_rascunho(db,
outbox_id, aprovado_via="janela_automatica")` — reaproveita a transação
existente em vez de duplicá-la. Editar a mensagem no Telegram (mesmo padrão de
`edit_message` que `expirar_rascunhos_pendentes` já faz) informando que foi
liberado automaticamente.

**8. `listar_rascunhos` passa a incluir `STATUS_AGUARDANDO_JANELA`** no filtro
(`where("status", "in", [STATUS_AGUARDANDO, STATUS_AGUARDANDO_JANELA])`) e a
expor `envio_liberado_em` no dicionário de cada rascunho — quem consome essa
lista (tool `listar_rascunhos_pendentes`, detector de aprovação por WhatsApp em
`atencao_whatsapp.py`) precisa continuar vendo os promovidos como "ainda em
jogo".

## O que muda em `functions/main.py`

Na função periódica que já chama `expirar_rascunhos_pendentes` (por volta da
linha 3800), adicionar a chamada a `liberar_rascunhos_promovidos(db,
agora=now)` **fora do `if now.minute == 0`** — a janela é de minutos, não faz
sentido só checar de hora em hora. Mesmo bloco `try/except` isolado que já
protege a chamada de expiração, para uma falha aqui não derrubar o resto do
tick.

## Nova coleção de sugestão + tool de decisão

Novo módulo `functions/promocao_autonomia.py` (não colocar dentro de
`outbox_aprovacao.py` nem de `retro_agente.py` — mesmo motivo de
`deteccao_subproduto.py` ser separado: lógica pura testável isolada de quem a
consome). Nova coleção `promocoes_autonomia_sugeridas`, **doc ID determinístico
= o próprio `tipo`** (sanitizado) — mais simples que o padrão de quota mensal de
`elevacoes_sugeridas`, porque aqui a garantia de não-duplicação é natural: um
tipo só pode ter uma sugestão em aberto por vez.

- `tipos_elegiveis_para_promocao(db, amostra_minima=8, taxa_minima=0.9,
  janela_recente=200) -> list[dict]`: varre os últimos `janela_recente`
  documentos de `whatsapp_outbox` com status em (`pending`, `sent`), agrupa por
  `tipo` em memória para descobrir quais tipos têm volume, e para cada um com
  contagem bruta >= `amostra_minima` chama `metricas_por_tipo(db, tipo,
  limite=20)` (reaproveita o PR 1 em vez de recalcular). Filtra fora: tipos já
  em `system/mcp_access.tipos_promovidos`, tipos com sugestão `pendente` ou
  `nunca` em `promocoes_autonomia_sugeridas` (sugestão `adiada` pode ser
  reavaliada). Devolve os que passam `taxa_sem_edicao >= taxa_minima`.
- `registrar_sugestao_promocao(db, tipo, metricas) -> str`: grava/sobrescreve o
  doc `promocoes_autonomia_sugeridas/{tipo}` com status `pendente` e as
  métricas que geraram a proposta (auditoria de por que foi sugerido).
- `decidir_promocao_autonomia(db, tipo, decisao: "aceitar"|"adiar"|"nunca") ->
  dict`: transacional, tocando os dois documentos (`promocoes_autonomia_sugeridas/{tipo}`
  e `system/mcp_access`) na mesma transação Firestore. Ao aceitar: status vira
  `aceita` **e** `tipo` é unido a `system/mcp_access.tipos_promovidos` na mesma
  escrita atômica — diferente de `decidir_elevacao`, que devolve instrução para
  o chamador executar depois (lá o efeito é externo/cross-system; aqui é uma
  escrita Firestore dentro do mesmo módulo, não precisa do indireção de dois
  passos).
- `listar_promocoes_pendentes(db) -> dict`: filtro de status no Firestore,
  mesmo formato de `listar_pendentes` em `deteccao_subproduto.py`.

**Hook no retro semanal** (`functions/retro_agente.py`,
`executar_retro_semanal`): chamar `tipos_elegiveis_para_promocao` e, para cada
elegível, `registrar_sugestao_promocao` — **fora do bloco do Gemini**, é
determinístico e não depende da análise LLM da semana. Limitar a no máximo 2
sugestões novas por execução (evita lotar o Telegram se vários tipos ficarem
elegíveis juntos). Se houver sugestão nova, acrescentar uma linha na mesma
mensagem informativa que a função já envia ao final (perto de onde hoje menciona
`proposta_pop`, por volta da linha 448) — não criar uma segunda mensagem nem
botões novos; é aviso, a decisão é via tool, igual `proposta_pop`.

## `functions/tools/hermes_tools.py` e schemas

Registrar `decidir_promocao_autonomia` e `consultar_promocoes_autonomia_sugeridas`
espelhando exatamente como `decidir_elevacao`/`_consultar_elevacoes_sugeridas`
já estão registradas (linhas ~107-117 e ~1995-1996) — mesmo padrão de wiring,
mesmo lugar.

## Testes (`functions/test_promocao_autonomia.py`, novo arquivo)

Reaproveitar `MockDb`/`MockQuery` de `test_atencao.py` (mesmo padrão do PR 1).
Cobrir: `avaliar_liberacao_promovidos` (dentro/fora da janela); `criar_rascunho`
indo para `aguardando_janela` quando o tipo está promovido e para
`aguardando_aprovacao` quando não está; `liberar_rascunhos_promovidos`
transicionando só os vencidos; cancelamento via `descartar_rascunho` funcionando
a partir de `aguardando_janela`; `tipos_elegiveis_para_promocao` com amostra
insuficiente (não elegível), tipo já promovido (excluído), sugestão `pendente`
existente (não duplica), sugestão `adiada` (reavaliada); `decidir_promocao_autonomia`
nos três desfechos, conferindo que só `aceitar` escreve em
`system/mcp_access.tipos_promovidos`. Estender `test_outbox_aprovacao.py` para
`listar_rascunhos` incluir `aguardando_janela`.

## Fora de escopo deste PR

Nenhuma mudança em `_CONFIRMACAO_OBRIGATORIA` nem no gate do canal MCP — é outro
mecanismo, para outro canal, e continua fora de alcance por configuração
(condição do dono, 02/09/2026). Nenhum botão novo no Telegram além do
`Cancelar` já existente. Filtragem de tools por canal de voz é o PR 3
(`voiceEnabled`/`orchestrator.py`), não entra aqui.
