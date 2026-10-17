"""Proveniência de fatos de memória (P06 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, seção "P06 — Memória e contexto
que não se contaminam", passo 1 do pacote: "Acrescentar proveniência e
validade aos novos fatos; ler memória antiga com origem legacy_unknown."

Lógica pura -- sem I/O, mesmo padrão incremental usado para abrir P04
(`autonomy/requests.py`) e P05 (`autonomy/events.py`): vocabulário e regra de
leitura primeiro, testável sem Firestore. Este módulo não decide ONDE o
campo é escrito (isso é `main._save_memory_node`) nem quem consome a
proveniência para responder (isso é `obter_contexto_operacional`/
`consultar_memoria_contextual`, passo 6 do pacote, ainda não implementados).

## Taxonomia

O passo 2 do pacote enumera as categorias, sem ambiguidade a resolver aqui:
"Separar explicitamente: declaração humana, fonte externa, resumo derivado,
inferência do agente e telemetria de uso." `ORIGENS_FATO_NOVO` é essa lista,
em código. `LEGADO_DESCONHECIDO` ("legacy_unknown") é o valor exigido pelo
próprio passo 1 para fatos gravados antes desta sub-entrega, que não têm
`origem_fato` nenhum gravado.

## Escopo desta sub-entrega (registrado aqui e no diário)

Só `main._save_memory_node` -- usado por `salvar_memoria_global` (tools/
hermes_tools.py, exposta tanto a clientes MCP quanto ao copiloto web) e por
`resolver_conflito_memoria` (MCP, callable `confirmarConflitoMemoria` e o
copiloto web) -- passa a gravar `origem_fato`. (Esta enumeração de
chamadores é de quando este módulo foi escrito, P06 sub-entrega 1/N -- a
sub-entrega seguinte, descrita abaixo, acrescenta um terceiro chamador,
`telegram_message_tools.py::salvar_memoria_global`.)

`resolver_conflito_memoria` só age após `ultima_decisao_humana` explícita
(o usuário escolhe `manter_existente`/`substituir_pelo_novo` depois que a
automação é obrigada a parar e perguntar) em QUALQUER canal -- por isso
`_save_memory_node` usa `DECLARACAO_HUMANA` como default do novo parâmetro
`origem_fato`, e nenhum dos chamadores desse caminho (main.py x2,
tools/telegram_extended.py) precisa passá-lo explicitamente.

`salvar_memoria_global`, ao contrário, tem DOIS contratos textuais
DIFERENTES para o MESMO código (`tools/hermes_tools.py::_salvar_memoria_global`),
um por canal -- achado real da 1a rodada de revisão adversarial desta
sub-entrega, que a versão original deste módulo não tinha enxergado ao
assumir `DECLARACAO_HUMANA` para os dois:
- `canal="mcp"` (servidor MCP Sistema-Hermes, `mcp_server.py`, texto de
  `_INSTRUCTIONS`): "Quando o usuário afirmar um fato durável... grave com
  `salvar_memoria_global`" -- exige afirmação do usuário por contrato.
  `DECLARACAO_HUMANA`.
- `canal="web"` (copiloto web, `main.py`, system prompt da closure
  `salvar_memoria_global`): "Quando identificar uma regra de negócio
  durável, uma preferência operacional estável ou um fato global útil...
  acione `salvar_memoria_global`... silenciosamente" -- o PRÓPRIO MODELO
  decide gravar por ter identificado um padrão, sem exigir que o usuário
  tenha dito aquilo literalmente. `INFERENCIA_AGENTE`.

`origem_fato_para_canal_de_salvar_memoria` resolve essa distinção a partir
de `ctx.canal` (`tools/tool_context.py`), sem inferir `tipo`/`origem_humana`
de `Principal` (`autonomy/contracts.py`) -- esses dois eixos respondem
perguntas diferentes (se há um humano supervisionando a sessão agora vs.
quem originou ESTE fato especificamente) e não devem ser confundidos, mesmo
quando a mesma sessão é `origem_humana=True` nos dois canais.

Achado real do Codex (revisão automática desta PR, comentário no commit
`0ab24ff`): no canal `"web"`, o USUÁRIO também pode afirmar um fato
literalmente (ex.: "prefiro reuniões de manhã") e o modelo só reage
chamando `salvar_memoria_global` -- isso é `DECLARACAO_HUMANA`, não
`INFERENCIA_AGENTE`, mesmo que o canal seja `"web"`. O canal sozinho não
distingue, DENTRO do mesmo canal, "o usuário disse isto" de "eu percebi
isto" -- só o modelo, no momento da chamada, sabe qual dos dois aconteceu.
`origem_fato_para_salvar_memoria` (abaixo) resolve isso pedindo ao PRÓPRIO
CHAMADOR (o parâmetro novo `usuario_afirmou_diretamente` da tool, preenchido
pelo modelo a cada chamada, não pelo código) em vez de adivinhar só pelo
canal -- `origem_fato_para_canal_de_salvar_memoria` continua existindo como
o FALLBACK quando esse parâmetro vem ausente/falso (comportamento anterior,
preservado para não quebrar um cliente MCP que ainda não manda o parâmetro
-- o contrato do servidor MCP já garante afirmação do usuário de qualquer
forma, então o fallback para canal="mcp" continua correto mesmo sem o
parâmetro).

## Sub-entrega seguinte (P06 sub-entrega 2/N)

`telegram_message_tools.py::salvar_memoria_global` (motor Telegram legado,
fallback quando o copiloto web falha) passou a chamar `_save_memory_node`
também -- terceiro chamador deste módulo, usando `canal="telegram"` em
`origem_fato_para_canal_de_salvar_memoria`. Esse canal não tinha sido
auditado quando este módulo foi escrito (ver pendência removida abaixo, que
esta sub-entrega resolve) -- cai no mesmo default de `INFERENCIA_AGENTE` já
documentado acima para "qualquer canal que não seja mcp", sem precisar de
nenhuma mudança neste módulo: a função já cobria esse caso por construção.
Diferente de `tools/hermes_tools.py::_salvar_memoria_global`, este chamador
NÃO usa `origem_fato_para_salvar_memoria`/`usuario_afirmou_diretamente` --
o texto desta ferramenta especificamente ("Apenas para regras estáveis e
preferências permanentes") não foi auditado quanto a exigir ou não
afirmação literal do usuário, então adicionar esse parâmetro extra é
trabalho de uma sub-entrega própria que faça essa auditoria primeiro, não
algo a assumir por semelhança com os outros dois canais.

NÃO tocado por esta sub-entrega, registrado como pendência:
- `knowledge_graph.py` (`_crystallize_task` e o fluxo de nós conceituais de
  procedimento): escreve em `knowledge_nodes` com uma FORMA DIFERENTE de
  documento (sem `tipo`/`texto_memoria`; nós de procedimento, não de fato) e
  corresponde ao passo 8 do pacote (mapa de POPs), não ao passo 1. Marcar
  esses nós como `resumo_derivado` é trabalho de uma sub-entrega própria que
  decida a forma final desses nós. (Ver "Sub-entrega seguinte (P06
  sub-entrega 4/N)" abaixo, que resolve isto.)
- "Validade" (a segunda metade do passo 1) corresponde ao passo 4 do pacote
  ("Modelar fatos temporais e relação supersedes") e não é modelada aqui --
  `memoria_status` já existe (sempre "ativa" hoje, nunca lido nem transicionado
  em nenhum lugar do código) e fica como está, sem colisão com este módulo.

## Sub-entrega seguinte (P06 sub-entrega 4/N)

`knowledge_graph.py` (`_dual_pass_find_or_create_node`, criação de nó, e
`_crystallize_task`, atualização de nó) passou a gravar `origem_fato=
RESUMO_DERIVADO` nos dois pontos de escrita de `knowledge_nodes` que
correspondem a nós de PROCEDIMENTO (não de fato) -- quarto chamador deste
módulo, e o primeiro que não passa por `_save_memory_node`/
`salvar_memoria_global`. Confirmado que NENHUMA decisão de schema nova era
necessária: esses nós já são discriminados dos nós de memória/fato pela
AUSÊNCIA do campo `tipo` (`main.py::MEMORY_NODE_TYPES` e
`_find_similar_memory_nodes` só consideram `tipo in {"regra_global",
"fato_isolado"}` -- um nó de procedimento nunca grava `tipo`, então nunca
colide com busca de memória/fato, antes ou depois desta sub-entrega) --
não foi preciso introduzir nenhum campo discriminador novo. O valor é
sempre `RESUMO_DERIVADO`, sem ramificação por chamador/canal (diferente de
`salvar_memoria_global`): um nó de procedimento é, por definição, um
resumo do diário de uma tarefa gerado por LLM, nunca uma declaração humana
direta. `origem_fato_de_leitura` (acima) já funciona sem nenhuma mudança
para esses nós -- é genérica a qualquer dict, não específica de uma
coleção ou forma de documento. Nenhum consumidor de leitura foi tocado
(mesmo estado do passo 6, "ainda não implementado", citado na docstring
original do módulo) -- esta sub-entrega só fecha a escrita, como as
anteriores fecharam a escrita dos outros três chamadores.
"""

from __future__ import annotations

DECLARACAO_HUMANA = "declaracao_humana"
FONTE_EXTERNA = "fonte_externa"
RESUMO_DERIVADO = "resumo_derivado"
INFERENCIA_AGENTE = "inferencia_agente"
TELEMETRIA_USO = "telemetria_uso"
LEGADO_DESCONHECIDO = "legacy_unknown"

# Categorias atribuíveis a um fato NOVO, gravado a partir desta sub-entrega
# (passo 2 do pacote P06, na ordem em que o passo as lista).
ORIGENS_FATO_NOVO = (
    DECLARACAO_HUMANA,
    FONTE_EXTERNA,
    RESUMO_DERIVADO,
    INFERENCIA_AGENTE,
    TELEMETRIA_USO,
)

# Todo valor que uma leitura pode legitimamente encontrar em `origem_fato`,
# incluindo o marcador de fato legado (passo 1: "ler memória antiga com
# origem legacy_unknown").
ORIGENS_FATO_VALIDAS = frozenset(ORIGENS_FATO_NOVO) | {LEGADO_DESCONHECIDO}


def origem_fato_de_leitura(doc: dict | None) -> str:
    """Proveniência de um documento de `knowledge_nodes` já lido do Firestore.

    Devolve o valor gravado em `origem_fato` quando ele é uma das categorias
    conhecidas; devolve `LEGADO_DESCONHECIDO` em qualquer outro caso --
    campo ausente (documento gravado antes desta sub-entrega), `None`, um
    valor que não pertence à taxonomia (gravação futura com um enum
    diferente, corrupção de dado), OU um tipo não-string (ex.: uma lista ou
    um dict gravados por engano em `origem_fato` -- Firestore aceita
    qualquer tipo, e a 1a versão desta função fazia `valor in
    ORIGENS_FATO_VALIDAS` sem checar o tipo antes, o que lança `TypeError:
    unhashable type` para uma lista/dict em vez de devolver o default
    seguro; achado real da 1a rodada de revisão adversarial desta
    sub-entrega). Nunca lança: uma leitura de memória não deve falhar por
    causa de um campo de proveniência ausente ou inesperado.
    """
    if not doc:
        return LEGADO_DESCONHECIDO
    valor = doc.get("origem_fato")
    if not isinstance(valor, str):
        return LEGADO_DESCONHECIDO
    return valor if valor in ORIGENS_FATO_VALIDAS else LEGADO_DESCONHECIDO


def origem_fato_para_canal_de_salvar_memoria(canal: str | None) -> str:
    """Proveniência de um fato NOVO criado via `salvar_memoria_global`
    (`tools/hermes_tools.py::_salvar_memoria_global`), a partir do `canal` do
    `ToolContext` que fez a chamada.

    Só resolve especialmente o canal `"mcp"` (ver docstring do módulo):
    `"mcp"` -> `DECLARACAO_HUMANA` (contrato do servidor MCP exige afirmação
    do usuário); qualquer outro canal (hoje `"web"`, o copiloto, e
    `"telegram"`, o motor Telegram legado -- ver "Sub-entrega seguinte"
    acima) -> `INFERENCIA_AGENTE` (o texto da tool nesses canais pede para o
    MODELO identificar o fato durável, sem exigir uma afirmação literal do
    usuário). Um canal novo que chegue a `salvar_memoria_global` no futuro
    cai no mesmo default de `INFERENCIA_AGENTE` até alguém auditar o texto
    do system prompt desse canal especificamente -- `DECLARACAO_HUMANA`
    nunca deve ser o default silencioso para um canal não auditado, porque é
    a afirmação mais forte das duas (fato literalmente dito pelo usuário).
    """
    return DECLARACAO_HUMANA if canal == "mcp" else INFERENCIA_AGENTE


def origem_fato_para_salvar_memoria(
    canal: str | None, usuario_afirmou_diretamente: bool = False
) -> str:
    """Proveniência de um fato NOVO criado via `salvar_memoria_global`,
    combinando o `canal` da chamada com `usuario_afirmou_diretamente` -- um
    parâmetro NOVO da própria tool (ver `tools/schemas/salvar_memoria_global.json`
    e as closures em `main.py`/`tools/hermes_tools.py`), que o MODELO que fez
    a chamada preenche a cada vez, declarando se FOI o usuário quem afirmou
    aquele fato literalmente nesta conversa.

    `usuario_afirmou_diretamente=True` -> `DECLARACAO_HUMANA`, em QUALQUER
    canal -- é a fonte mais confiável que existe (o próprio chamador, que viu
    a conversa, afirma que o usuário disse aquilo). Caso contrário (`False`
    ou parâmetro ausente, ex.: um cliente MCP mais antigo que ainda não
    manda esse campo), cai no fallback de `origem_fato_para_canal_de_salvar_memoria`
    -- que já trata canal="mcp" como declaração humana por contrato, e
    qualquer outro canal como inferência do agente.

    Nunca o inverso (um canal "mcp" com `usuario_afirmou_diretamente=False`
    virar `INFERENCIA_AGENTE`): o contrato do servidor MCP já exige afirmação
    do usuário para esta tool ser chamada, então um cliente que simplesmente
    ainda não envia o parâmetro não deve perder a classificação correta que
    o canal sozinho já garantia antes deste parâmetro existir.
    """
    if usuario_afirmou_diretamente:
        return DECLARACAO_HUMANA
    return origem_fato_para_canal_de_salvar_memoria(canal)


def origem_fato_para_salvar_pop(
    usuario_forneceu_o_texto: bool | None = None,
    origem_fato_existente: str | None = None,
) -> str:
    """Proveniência de um POP novo/atualizado via `salvar_pop_global`
    (`tools/telegram_extended.py`), a partir de `usuario_forneceu_o_texto` --
    parâmetro NOVO da própria tool (ver
    `tools/schemas/salvar_pop_global.json`), que o MODELO que fez a chamada
    preenche a cada vez, declarando se foi o USUÁRIO quem forneceu o texto
    do procedimento literalmente (copiou/colou, ditou, ou escreveu palavra
    por palavra) nesta conversa.

    `origem_fato_existente` é o `origem_fato` JÁ GRAVADO no documento, só
    relevante numa ATUALIZAÇÃO (merge sobre um POP existente, mesmo título
    ou mesmo gatilho) -- `None` numa criação, onde não há nada a preservar.
    Achado real de revisão adversarial independente (sessão de 17/10/2026,
    fora das 7 rodadas originais desta sub-entrega): sem este parâmetro, uma
    chamada de ATUALIZAÇÃO que omita `usuario_forneceu_o_texto_literal` (ex.:
    um segundo gatilho acrescentado ao mesmo POP, numa conversa onde o
    modelo simplesmente não repete o slot opcional) cairia no mesmo default
    `DECLARACAO_HUMANA` de uma criação nova -- sobrescrevendo em silêncio um
    `INFERENCIA_AGENTE` corretamente rebaixado por uma chamada anterior. Isso
    é exatamente a superestimação de proveniência que esta função existe
    para eliminar, só que pela porta de trás do caminho de update: a lacuna
    está na ausência de informação nova sobre uma atualização, não na
    criação de um fato sem proveniência alguma ainda registrada (o caso que
    a analogia original com `canal="mcp"` cobre).

    Acrescentada DEPOIS da PR original de `salvar_pop_global` gravar
    `origem_fato`, em resposta a um achado real do Codex (revisão
    automática, comentário "Derive POP provenance from its actual author"):
    o contrato textual desta tool no servidor MCP (`mcp_server.py`,
    `_handle_prompts_list`: "Um POP é um procedimento operacional que o
    usuário já escreveu") pressupõe que o texto sempre vem do usuário -- mas,
    na prática, um cliente MCP pode pedir ao modelo para CRIAR ou REFINAR um
    POP a partir de uma descrição vaga, e é o próprio modelo quem redige o
    `instrucao_sistema` final. Gravar `DECLARACAO_HUMANA` incondicionalmente
    nesse caso superestima a proveniência -- o texto nunca foi dito/escrito
    pelo usuário palavra por palavra.

    `usuario_forneceu_o_texto is None` (parâmetro ausente, ex.: um cliente
    MCP mais antigo que ainda não manda esse campo) preserva o comportamento
    anterior a esta correção (`DECLARACAO_HUMANA`) -- mesma lógica do
    fallback canal="mcp" em `origem_fato_para_canal_de_salvar_memoria`: o
    contrato do servidor MCP já pressupõe afirmação do usuário por padrão,
    então a mera AUSÊNCIA do parâmetro não deve, por si só, rebaixar uma
    classificação que já existia antes dele.

    Com o parâmetro PRESENTE, só o literal Python `True` (`is True`, não
    `bool(...)`) devolve `DECLARACAO_HUMANA` -- qualquer outro valor devolve
    `INFERENCIA_AGENTE`, inclusive tipos "parecidos com False" só por
    coincidência de truthiness. Achado real de revisão adversarial sobre a
    1a versão desta correção: nada neste codebase valida/coage o JSON de
    entrada contra o schema MCP antes de chegar aqui (mesmo raciocínio já
    registrado em `tools/hermes_tools.py::_salvar_memoria_global` para
    `usuario_afirmou_diretamente`) -- `bool("false")` é `True` em Python, e a
    1a versão deste helper comparava só com `is False`, o que deixava a
    STRING `"false"` (ou `0`, ou qualquer valor que não seja o bool `True`
    exato) cair no `else` e gravar `DECLARACAO_HUMANA` -- exatamente a
    superestimação de proveniência que este helper existe para eliminar. A
    direção seguro aqui é a OPOSTA da de `sempre_ativo`
    (`tools/telegram_extended.py`, que usa `is True` para o lado "mais
    forte" ser o booleano explícito e tudo o mais cair no lado fraco/padrão
    `False`): aqui a reivindicação mais forte é `DECLARACAO_HUMANA`, então só
    o `True` exato a concede -- `False` explícito E qualquer valor
    ambíguo/mal-tipado caem igualmente no lado fraco `INFERENCIA_AGENTE`,
    nunca no lado forte.
    """
    if usuario_forneceu_o_texto is None:
        if isinstance(origem_fato_existente, str) and origem_fato_existente in ORIGENS_FATO_VALIDAS:
            return origem_fato_existente
        return DECLARACAO_HUMANA
    return DECLARACAO_HUMANA if usuario_forneceu_o_texto is True else INFERENCIA_AGENTE
