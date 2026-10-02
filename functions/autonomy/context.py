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
copiloto web) -- passa a gravar `origem_fato`.

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

NÃO tocado por esta sub-entrega, registrado como pendência:
- `knowledge_graph.py` (`_crystallize_task` e o fluxo de nós conceituais de
  procedimento): escreve em `knowledge_nodes` com uma FORMA DIFERENTE de
  documento (sem `tipo`/`texto_memoria`; nós de procedimento, não de fato) e
  corresponde ao passo 8 do pacote (mapa de POPs), não ao passo 1. Marcar
  esses nós como `resumo_derivado` é trabalho de uma sub-entrega própria que
  decida a forma final desses nós.
- `telegram_message_tools.py::salvar_memoria_global` (motor Telegram legado,
  fallback quando o copiloto web falha -- ver `telegram_handlers_core.py`,
  "Fallback para motor Telegram"): escreve direto em `knowledge_nodes` com um
  esquema PRÓPRIO e divergente (`fato`/`categoria`/`origem` como campos
  soltos, sem embedding, sem dedup, sem passar por `_save_memory_node`).
  Descoberta ao investigar esta sub-entrega; não corrigida aqui porque
  unificar os dois caminhos de escrita é maior que "acrescentar um campo" --
  candidato a achado/pendência próprio.
- "Validade" (a segunda metade do passo 1) corresponde ao passo 4 do pacote
  ("Modelar fatos temporais e relação supersedes") e não é modelada aqui --
  `memoria_status` já existe (sempre "ativa" hoje, nunca lido nem transicionado
  em nenhum lugar do código) e fica como está, sem colisão com este módulo.
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

    Só resolve os dois canais que hoje chegam a essa tool (ver docstring do
    módulo): `"mcp"` -> `DECLARACAO_HUMANA` (contrato do servidor MCP exige
    afirmação do usuário); qualquer outro canal (hoje só `"web"`, o copiloto)
    -> `INFERENCIA_AGENTE` (o system prompt do copiloto web pede para o
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
