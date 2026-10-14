"""Fatos temporais e relação supersedes (P06 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, pacote P06, passo 4: "Modelar
fatos temporais e relação supersedes; correção invalida derivados e
checkpoints de planos afetados.").

Lógica pura -- sem I/O, mesmo padrão incremental de `autonomy/context.py`
(P06 sub-entrega 1/N) e `autonomy/events.py`/`autonomy/requests.py`
(P04/P05): vocabulário e payloads primeiro, testável sem Firestore. Este
módulo não decide ONDE os documentos são escritos ou lidos -- isso é
`main._save_memory_node` (escrita) e `main._find_similar_memory_nodes` /
`copilot_context._format_recent_memories` / `telegram_handlers_core.py`
(leitura), fiados nesta mesma sub-entrega (ver docstrings lá).

## O que é "supersedes" aqui

Antes desta sub-entrega, `main._save_memory_node` (branch `force_update_id`,
usado por `resolver_conflito_memoria` -- copiloto web e MCP -- quando a
decisão humana é `substituir_pelo_novo`) sobrescrevia o documento vivo em
`knowledge_nodes/{force_update_id}` com `ref.set(..., merge=True)`:
`texto_memoria`/`resumo`/`embedding` do fato ANTIGO eram perdidos para
sempre. A função já lia o conteúdo antigo (`current`) para devolver
`previous_text` na resposta, mas nunca persistia em lugar nenhum --
pendência documentada em `autonomy/context.py` (linhas ~104-107) e remetida
explicitamente ao passo 4.

Este módulo modela a correção SEM mudar o `memory_id` que os chamadores de
`_save_memory_node(force_update_id=...)` (`main.py::resolver_conflito_memoria`,
closure do copiloto web; `main.py::confirmarConflitoMemoria`, callable
separado; `tools/telegram_extended.py`, mesmo caminho) já dependem de
receber de volta -- todos tratam `force_update_id` como o id que CONTINUA
sendo o do documento vivo após a substituição (ver
`verificadores_escrita.py::resolver_conflito_memoria`, que verifica
`knowledge_nodes/{memory_id}` com o MESMO id enviado, e
`test_memoria_origem_fato.py::test_resolver_conflito_substituir_pelo_novo_grava_declaracao_humana`,
que lê o doc pelo MESMO `force_update_id`). Mudar o id quebraria a UI do
copiloto web e o verificador de escrita -- fora de escopo para esta
sub-entrega, que é sobre MODELAR a relação, não sobre redesenhar a API.

Em vez disso: no momento da substituição, o conteúdo ANTIGO (os mesmos
campos que `_save_memory_node` já lia para `previous_text`, antes de
descartá-los) vira um documento HISTÓRICO NOVO, com um id novo (mesmo padrão
`uuid.uuid4()[:12]` já usado para fatos novos), marcado
`memoria_status=STATUS_SUPERADA` e `superada_por=<id do documento vivo>`.
O documento vivo (o MESMO `force_update_id`, contrato preservado) ganha
`supersedes=<id do documento histórico>` -- dois nós ligados por uma relação
explícita, em vez de um fato apagado silenciosamente.

`payload_documento_historico` copia TODOS os campos do snapshot anterior
(cópia defensiva, `dict(conteudo_anterior)`) e só sobrescreve os campos de
status/relação/auditoria da transição -- em particular, NÃO toca
`data_criacao`: o documento histórico preserva a data de criação do fato
ORIGINAL, não a data da substituição (isso importa para os pontos de leitura
ordenados por `data_criacao DESC` descritos abaixo -- o histórico não deve
parecer "recente" só porque a cópia foi gravada agora).

## memoria_status

`STATUS_ATIVA` ("ativa") é o valor que TODO documento de `knowledge_nodes`
já carrega hoje (`main._save_memory_node` grava isso em todo fato novo e em
toda substituição, desde antes desta sub-entrega) -- `memoria_status_de_leitura`
abaixo é a leitura defensiva simétrica a `origem_fato_de_leitura`
(`autonomy/context.py`): documento ausente, campo ausente (todo fato gravado
antes de QUALQUER sub-entrega de P06 nunca teve `memoria_status` nenhum --
ver pendência removida em `autonomy/context.py`, linha ~106: "memoria_status
já existe... sempre 'ativa' hoje, nunca lido nem transicionado"), `None`,
tipo inesperado (lista/dict -- mesmo achado de robustez de
`origem_fato_de_leitura`, tratado aqui pelo mesmo motivo: Firestore aceita
qualquer tipo no campo, e uma leitura de memória não deve lançar por um dado
corrompido) ou valor fora da taxonomia -- todos caem em `STATUS_ATIVA`,
nunca em `STATUS_SUPERADA`. Isso é seguro porque o universo de documentos
escritos ANTES desta sub-entrega é 100% "ativa" por definição (nenhum código
anterior a esta sub-entrega jamais escreveu `STATUS_SUPERADA`) -- o default
de uma leitura desconhecida é o MESMO valor que já estava implícito, nunca
um valor novo que mudaria silenciosamente o comportamento de busca/retrieval
para documentos antigos.

## O que NÃO é modelado aqui (pendências explícitas, registradas também em
docs/autonomia/execucao.md)

- "Correção invalida derivados": nenhum "derivado" (resumo/síntese calculado
  A PARTIR de um fato) é rastreado hoje em lugar nenhum do código -- não há
  estrutura de onde invalidar nada. Pendência completa.
- "checkpoints de planos afetados": o único conceito de "checkpoint" que
  existe (`autonomy/ledger.py`, pacote P04) é sobre checkpoints de OPERAÇÕES
  AUTÔNOMAS, não de planos de ação do produto (`plano_acao`) -- não há
  infraestrutura para conectar um fato superado a um plano de ação afetado.
  Pendência completa, mesmo padrão do passo 8/POPs que a sub-entrega 1/N já
  deixou como pendência explícita.
- Pontos de leitura de `knowledge_nodes` fiados a `memoria_status` nesta
  sub-entrega: `main._find_similar_memory_nodes` (decide conflito/duplicata
  -- o caminho mais crítico, por isso priorizado),
  `copilot_context._format_recent_memories` e o bloco "MEMÓRIA GLOBAL ATIVA"
  de `telegram_handlers_core.py` (ambos ordenam por `data_criacao` DESC e
  injetam fatos "recentes" no contexto do modelo -- filtrados por defesa em
  profundidade, mesmo com `data_criacao` preservado no histórico). NÃO
  fiado: `knowledge_graph.py::_search_nodes` e o vector search de
  procedimentos em `main.py` (`buscar_procedimento_internal`) -- ambos
  operam sobre nós de PROCEDIMENTO (forma de documento diferente, sem
  `tipo`/`texto_memoria`), já excluídos do passo 1 por `autonomy/context.py`
  e fora do escopo do passo 4 pelo mesmo motivo.

## LIMITAÇÃO DESCOBERTA NESTA SUB-ENTREGA: `main.py` não pôde ser editado

A fiação em `main._save_memory_node`/`main._find_similar_memory_nodes`
descrita acima foi IMPLEMENTADA e VERIFICADA localmente (suíte completa
passou com ela ativa), mas NÃO PÔDE SER PUBLICADA nesta PR:
`functions/main.py` tem ~726.000 caracteres, muito acima do limite de
200.000 caracteres da tool de escrita do Argos (confirmado por um teste
real contra o branch desta sub-entrega, não só pelo limite documentado no
schema). É o MESMO motivo (~64000 tokens de saída por chamada de escrita),
na mesma ordem de grandeza, que levou a dividir `hermes_core_logic.py` e
`telegram_utils.py` no P02 (decisão do André de 2026-09-08) -- `main.py`
nunca foi dividido do mesmo jeito e também cresceu além desse teto. Isso
bloqueia QUALQUER sub-entrega futura que precise editar `main.py` por essa
tool, não só esta -- registrado com prioridade em
docs/autonomia/execucao.md. O diff pretendido (import deste módulo em
`main.py`, filtro de `STATUS_SUPERADA` nas duas listas de candidatos de
`_find_similar_memory_nodes`, e a criação do documento histórico no branch
`force_update_id` de `_save_memory_node`, usando exatamente as funções
`payload_documento_historico`/`payload_documento_vivo_apos_substituicao`
abaixo) está registrado no relatório desta sub-entrega para quando
`main.py` for dividido ou a tool de escrita ganhar suporte a arquivo
grande/patch.
"""

from __future__ import annotations

STATUS_ATIVA = "ativa"
STATUS_SUPERADA = "superada"

STATUS_VALIDOS = frozenset({STATUS_ATIVA, STATUS_SUPERADA})


def memoria_status_de_leitura(doc: dict | None) -> str:
    """`memoria_status` de um documento de `knowledge_nodes` já lido do
    Firestore. Devolve `STATUS_SUPERADA` só quando o campo está gravado
    exatamente com esse valor; qualquer outro caso (documento ausente,
    campo ausente, `None`, tipo não-string, valor fora de `STATUS_VALIDOS`)
    devolve `STATUS_ATIVA` -- ver "memoria_status" no docstring do módulo
    para o porquê desse default ser seguro. Nunca lança: uma leitura de
    memória não deve falhar por causa de um campo de status ausente ou
    inesperado (mesmo padrão defensivo de `origem_fato_de_leitura`, incluindo
    o cuidado de checar `isinstance(..., str)` ANTES de comparar contra o
    frozenset -- um valor não-hasheável, como lista ou dict, gravado por
    engano em `memoria_status` lançaria `TypeError: unhashable type` num
    `valor in STATUS_VALIDOS` direto sem essa checagem)."""
    if not doc:
        return STATUS_ATIVA
    valor = doc.get("memoria_status")
    if not isinstance(valor, str):
        return STATUS_ATIVA
    return valor if valor in STATUS_VALIDOS else STATUS_ATIVA


def payload_documento_historico(
    *, conteudo_anterior: dict, novo_id: str, supersedido_por: str, agora: str
) -> dict:
    """Payload COMPLETO (para `set` sem merge, no documento NOVO cujo id é
    `novo_id`) do documento HISTÓRICO que nasce quando um fato vivo é
    substituído (`_save_memory_node(force_update_id=...)` com decisão
    `substituir_pelo_novo`).

    `conteudo_anterior` é o dict LIDO do documento vivo ANTES da
    substituição (o que `_save_memory_node` já lia para `previous_text` e
    descartava) -- este payload preserva TODOS os campos desse snapshot
    (cópia defensiva, `dict(...)`, nunca o objeto original) e sobrescreve só
    os campos de status/relação/auditoria da transição, para que o
    histórico continue buscável/legível com a mesma forma de um fato normal
    (mesmo `tipo`, `texto_memoria`, `embedding`, `data_criacao` original
    etc.) -- só "morto".

    `novo_id` sobrescreve o campo `id` herdado de `conteudo_anterior` --
    achado real da revisão adversarial desta sub-entrega: todo documento
    vivo sempre grava `"id"` igual ao seu PRÓPRIO id de documento
    (`force_update_id`, estável através de qualquer número de
    substituições), então `conteudo_anterior["id"]` é SEMPRE o id do
    documento vivo, nunca o do histórico que está nascendo agora -- sem essa
    sobrescrita, todo documento histórico ficaria com `id` apontando de
    volta para o vivo que o supersedeu, em vez do próprio id. Nada no código
    lê esse campo (`snap.id`/`ref.id` é usado em todo lugar, nunca
    `data["id"]`) então isso não quebra nenhum comportamento hoje, mas é um
    dado incoerente que uma leitura futura (ou uma inspeção manual no
    console do Firestore) encontraria.

    `supersedido_por` é o id do documento VIVO (o mesmo `force_update_id`
    recebido por `_save_memory_node`) -- numa cadeia de substituições
    sucessivas sobre o MESMO `force_update_id`, cada histórico nessa cadeia
    tem o MESMO `superada_por` (o id do vivo, estável), o que é correto: o
    vivo é quem o supersedeu no momento em que cada histórico nasceu, mesmo
    que o conteúdo do vivo mude de novo depois. `agora` é o timestamp ISO
    da substituição (`main._iso_now_utc()`), usado tanto para
    `validade_fim` (quando o fato histórico deixou de valer) quanto para
    `data_atualizacao` (quando este documento histórico em si foi escrito --
    distinto de `data_criacao`, que este payload NÃO toca).

    Nota sobre cadeias: se `conteudo_anterior` já tinha `supersedes` (ou
    seja, o vivo já havia sido substituído antes), esse campo é preservado
    tal qual -- o histórico resultante continua apontando para o histórico
    AINDA MAIS antigo que ele próprio havia superado quando estava vivo,
    formando uma cadeia encadeada em vez de perder a lineage."""
    historico = dict(conteudo_anterior)
    historico["id"] = novo_id
    historico["memoria_status"] = STATUS_SUPERADA
    historico["superada_por"] = supersedido_por
    historico["validade_fim"] = agora
    historico["data_atualizacao"] = agora
    return historico


def payload_documento_vivo_apos_substituicao(supersedes: str, agora: str) -> dict:
    """Payload PARCIAL (para `merge=True` no documento vivo) com os campos
    da relação `supersedes`, a ACRESCENTAR aos campos de conteúdo novo que
    `_save_memory_node` já monta (`texto_memoria`/`resumo`/`embedding`/
    `memoria_status=STATUS_ATIVA`/etc.) -- não os substitui. `supersedes` é
    o id do documento histórico que acabou de nascer
    (`payload_documento_historico` acima); `agora` é o mesmo timestamp da
    substituição, gravado aqui como `validade_inicio` (quando o conteúdo
    atual do documento vivo passou a valer)."""
    return {
        "supersedes": supersedes,
        "validade_inicio": agora,
    }
