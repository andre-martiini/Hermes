"""Ledger de operações e checkpoints (P04 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, seção 4.5 "Reserva, retomada e
idempotência", passo 3 do pacote: "Criar ledger de operações e checkpoints
com limites de tamanho").

Lógica pura -- sem I/O, mesmo padrão incremental de `autonomy/requests.py`
(P04 sub-entrega 1/N): tipos e regras primeiro (testável sem Firestore),
wiring numa sub-entrega seguinte. `agent_requests.py` continua sendo a única
fonte que fala com Firestore hoje; nada aqui é chamado em produção ainda.

Cobre três itens da seção 4.5:

6. "Antes de qualquer efeito, criar/reusar operation_ledger com chave única e
   hash canônico." -> `criar_ou_reusar_entrada`.
9. "Reentrega do mesmo pedido retorna trabalho em curso ou resultado já
   observado." -> `consultar_reentrega`.
10. "Se o mesmo idempotency_key vier com payload diferente, retornar
    conflito; nunca sobrescrever." -> `ConflitoIdempotencia`, levantado por
    `criar_ou_reusar_entrada`.

Este módulo é deliberadamente independente de `RequestStatus`
(`autonomy/requests.py`): o ledger de uma OPERAÇÃO (efeito externo dentro de
um pedido -- ver seção 4.2, "Operação externa") é um conceito mais estreito
que o estado do PEDIDO inteiro, e pode ter várias operações associadas a um
único pedido. Quem fizer o wiring decide como as duas máquinas se
relacionam; este módulo só garante a idempotência da operação em si.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any

from .requests import _exigir_tz_aware

#: Seção 4.5, passo 3: "checkpoints com limites de tamanho" -- o plano não
#: define o limite exato. Ponto de partida razoável: Firestore limita um
#: documento inteiro a 1MiB: 64KiB por checkpoint individual dá folga
#: generosa para o restante do documento (lease, status, outros
#: checkpoints) caber no mesmo doc quando o wiring persistir isto junto do
#: pedido.
MAX_CHECKPOINT_BYTES = 64 * 1024

#: Número máximo de checkpoints retidos por operação. Sem isto, uma operação
#: de longa duração com heartbeats/checkpoints frequentes cresceria sem
#: limite. Ao exceder, o(s) checkpoint(s) mais antigo(s) são descartados
#: (FIFO) -- ver `adicionar_checkpoint`. O propósito do checkpoint é permitir
#: retomada após queda (seção 4.5, item 8), não um histórico completo, então
#: descartar os mais antigos é seguro.
MAX_CHECKPOINTS_POR_OPERACAO = 20

#: Orçamento CUMULATIVO de bytes para o conjunto de checkpoints retidos --
#: achado do Codex (P2) na PR #328: `MAX_CHECKPOINTS_POR_OPERACAO *
#: MAX_CHECKPOINT_BYTES` sozinho permite até 20 * 64KiB = 1.310.720 bytes,
#: que sozinho já excede o limite de 1MiB (1.048.576 bytes) de um documento
#: Firestore -- antes mesmo de contar lease, status e os outros campos que
#: dividem o mesmo documento quando o wiring persistir isto. 512KiB dá folga
#: generosa para o resto do documento. Ver `_aplicar_orcamento_cumulativo`.
MAX_CHECKPOINTS_BYTES_TOTAL = 512 * 1024


class ConflitoIdempotencia(Exception):
    """Mesmo `idempotency_key`, payload com hash diferente -- seção 4.5,
    item 10: "retornar conflito; nunca sobrescrever." Quem pega esta
    exceção deve devolver conflito ao consumidor; a entrada existente no
    ledger não é alterada (esta exceção é levantada ANTES de qualquer
    tentativa de gravação)."""

    def __init__(self, idempotency_key: str, hash_existente: str, hash_novo: str) -> None:
        self.idempotency_key = idempotency_key
        self.hash_existente = hash_existente
        self.hash_novo = hash_novo
        super().__init__(
            f"idempotency_key '{idempotency_key}' já tem uma entrada no ledger com "
            f"payload diferente (hash existente={hash_existente!r}, hash novo="
            f"{hash_novo!r}) -- conflito, nunca sobrescrever (seção 4.5, item 10)."
        )


class CheckpointMuitoGrande(Exception):
    """Checkpoint excede `MAX_CHECKPOINT_BYTES` -- seção 4.5, passo 3:
    "checkpoints com limites de tamanho". Quem pega esta exceção deve
    reduzir o checkpoint (ex.: guardar uma referência/resumo em vez do
    payload inteiro), não tentar contornar o limite."""

    def __init__(self, tamanho_bytes: int, limite_bytes: int) -> None:
        self.tamanho_bytes = tamanho_bytes
        self.limite_bytes = limite_bytes
        super().__init__(
            f"checkpoint com {tamanho_bytes} bytes excede o limite de "
            f"{limite_bytes} bytes."
        )


def _chave_no_espirito_json(chave: Any) -> str:
    """Stringifica uma chave de dict com a MESMA regra que o encoder padrão
    do `json` usa internamente para chave não-string -- achado do Codex
    (P2) na PR #328: `str(chave)` NÃO bate com essa regra para `bool` e
    `None` (`str(True) == "True"`, mas `json.dumps({True: "x"})` produz
    `{"true": "x"}`; `str(None) == "None"`, mas o round-trip real produz
    `"null"`). Sem esta função, dois payloads que representam o MESMO
    conteúdo antes e depois de um round-trip real por JSON (ex.: um
    consumidor que serializa o pedido, manda pela rede, e o servidor
    desserializa antes de repassar para este módulo) produziam hashes
    DIFERENTES -- uma reentrega legítima virava `ConflitoIdempotencia` --, e
    o inverso também: `{None: "a", "None": "b"}` (duas chaves de verdade
    DIFERENTES em Python) era rejeitado como colisão quando, depois de um
    round-trip JSON real, só `"None"` (string) sobrevive como chave (a chave
    `None` vira `"null"`, não colide com a string `"None"`).

    `bool` é verificado ANTES de `int` (`isinstance(True, int)` é `True` em
    Python -- `bool` é subclasse de `int`). `float` usa `json.dumps` do
    valor (não da chave) para reaproveitar a MESMA regra de serialização
    numérica que o resto do módulo já usa para valores (inclusive
    NaN/Infinity, que `json.dumps` aceita como extensão não-padrão por
    default). `int` usa `repr` (equivalente ao que o encoder padrão do
    `json` produz para chave inteira)."""
    if isinstance(chave, str):
        return chave
    if isinstance(chave, bool):
        return "true" if chave else "false"
    if chave is None:
        return "null"
    if isinstance(chave, float):
        return json.dumps(chave)
    if isinstance(chave, int):
        return repr(chave)
    raise TypeError(
        f"chave de tipo {type(chave).__name__} não tem uma representação "
        f"JSON de chave definida: {chave!r}"
    )


def _canonicalizar_chaves(valor: Any) -> Any:
    """Converte toda chave de `dict` (em qualquer nível de aninhamento) para
    a representação de chave JSON (`_chave_no_espirito_json`) antes da
    serialização -- achado da 1a rodada de revisão adversarial (P04
    sub-entrega 2/N): `json.dumps(..., sort_keys=True)` levanta `TypeError`
    ao tentar ORDENAR um dict com chaves de tipos mistos (`{1: "a", "b":
    "c"}`), mesmo esse dict sendo perfeitamente serializável em JSON sem
    `sort_keys` (`json.dumps` já converte chave não-string para string
    silenciosamente nesse caso). Sem esta normalização prévia, um payload
    aninhado plausível (ex.: agrupado por ID numérico junto de uma
    chave-sentinela string) quebrava a canonicalização mesmo sendo um
    payload legítimo -- não um caso de "quem montou o payload errado".
    Converter ANTES de ordenar evita a colisão de tipos na comparação; JSON
    de verdade só tem chave string mesmo, então isto só antecipa uma
    normalização que já aconteceria no round-trip pela rede.

    Levanta `ValueError` se DUAS chaves DISTINTAS do MESMO dict colidirem
    depois de normalizadas (ex.: `{1: "x", "1": "y"}`) -- achado da 2a
    rodada de revisão adversarial (P04 sub-entrega 2/N): sem esta checagem,
    um dict comprehension simples faz "o último valor escrito vence" e
    descarta silenciosamente a outra entrada, encolhendo o payload sem
    aviso -- pior que o `TypeError` original, porque dois payloads
    OBJETIVAMENTE diferentes (um com a chave colidida, outro sem) passavam
    a produzir o MESMO hash, e `criar_ou_reusar_entrada` tratava um pedido
    que perdeu dado como reuso legítimo de uma entrada com o dado
    completo. Duas chaves de dicts DIFERENTES que colidem (comparadas em
    `hash_canonico`/`_mesmo_valor_canonico`, não dentro do mesmo dict)
    continuam sendo tratadas como equivalentes -- esse caso é intencional
    (ver `test_chave_int_e_chave_str_equivalente_colidem_apos_normalizacao`),
    só a perda de dado DENTRO do mesmo dict é um bug.

    Checa `Mapping` (não só `dict`): `Checkpoint.dados`/`LedgerEntry.resultado`
    já frozen por `_congelar_profundamente` (armazenados como
    `MappingProxyType`, não `dict`) passam por esta função de novo sempre
    que `_serializar_canonico` roda sobre eles (ex.: numa comparação de
    reentrega) -- `MappingProxyType` não é subclasse de `dict`, então checar
    só `dict` faria essas chamadas caírem no branch `else` e quebrar em
    `json.dumps`."""
    if isinstance(valor, Mapping):
        canonicalizado: dict[str, Any] = {}
        for chave, item in valor.items():
            chave_str = _chave_no_espirito_json(chave)
            if chave_str in canonicalizado:
                raise ValueError(
                    f"payload tem chaves distintas que colidem após normalização "
                    f"para a representação de chave JSON: {chave_str!r} (ex.: uma "
                    "chave int e uma chave str equivalentes no mesmo dict) -- "
                    "normalizar perderia dado silenciosamente; normalize as chaves "
                    "antes de chamar este módulo."
                )
            canonicalizado[chave_str] = _canonicalizar_chaves(item)
        return canonicalizado
    if isinstance(valor, (list, tuple)):
        return [_canonicalizar_chaves(item) for item in valor]
    return valor


def _serializar_canonico(valor: Any) -> str:
    """Serialização JSON canônica de qualquer valor (não só `dict` no
    nível mais alto) -- base compartilhada de `hash_canonico` e
    `_mesmo_valor_canonico`. Chaves ordenadas recursivamente em todos os
    níveis de aninhamento (após `_canonicalizar_chaves`), sem espaços
    supérfluos (`separators=(",", ":")`), para que o MESMO conteúdo lógico
    sempre produza a MESMA serialização independentemente da ordem de
    inserção das chaves em memória. Valor não-serializável em JSON (ex.:
    contém um objeto arbitrário) levanta `TypeError` -- isso é
    responsabilidade de quem monta o valor (código interno), não um caso a
    normalizar aqui."""
    return json.dumps(
        _canonicalizar_chaves(valor), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def _mesmo_valor_canonico(a: Any, b: Any) -> bool:
    """Igualdade "mesmo valor observável por quem consome o resultado",
    usada para decidir se uma reentrega repete EXATAMENTE o valor anterior
    -- não `a == b` do Python. Duas diferenças deliberadas em relação a
    `==`, ambas achados da 1a rodada de revisão adversarial (P04 sub-entrega
    2/N):

    1. `float("nan") == float("nan")` é `False` em Python (semântica IEEE
       754), então comparar resultado por `==` fazia uma reentrega
       IDÊNTICA (mesmo NaN reenviado) ser tratada como conflito, ao invés
       do no-op idempotente que o item 9 promete -- exatamente o cenário
       que este módulo existe para cobrir. Comparar pela serialização
       (`"NaN"` == `"NaN"` como string) resolve isso.
    2. `True == 1` é `True` em Python (bool é subclasse de int), mas
       `hash_canonico` já trata bool e int como payloads DIFERENTES (ver
       testes) -- usar `==` aqui criaria duas regras de "mesmo valor"
       incompatíveis dentro do mesmo módulo para o mesmo tipo de decisão.
       Comparar pela serialização (`"true"` != `"1"`) mantém a mesma regra
       nos dois lugares."""
    return _serializar_canonico(a) == _serializar_canonico(b)


def hash_canonico(payload: dict[str, Any]) -> str:
    """Hash SHA-256 determinístico de `payload` -- seção 4.5, item 6:
    "chave única e hash canônico." Ver `_serializar_canonico` para a
    canonicalização usada.

    RISCO ACEITO, documentado (não corrigido -- comportamento inerente a
    JSON, não um bug deste módulo): `1` (int) e `1.0` (float) produzem
    hashes DIFERENTES (`json.dumps` serializa como `"1"` e `"1.0"`), então
    um cliente que reenviar o "mesmo" pedido lógico trocando o tipo
    numérico (ex.: um proxy que sempre serializa número como float) recebe
    `ConflitoIdempotencia` em vez de reuso. Normalizar tipo numérico
    exigiria decidir uma política de coerção que o plano não especifica;
    quem fizer o wiring deve estar ciente e, se necessário, normalizar o
    payload ANTES de chamar este módulo."""
    return hashlib.sha256(_serializar_canonico(payload).encode("utf-8")).hexdigest()


def _congelar_profundamente(valor: Any) -> Any:
    """Converte um valor já passado por `json.loads` (só contém `dict`,
    `list`, `str`, `int`, `float`, `bool`, `None`) numa estrutura
    RECURSIVAMENTE imutável: `dict` vira `MappingProxyType` (view
    somente-leitura, recursiva) e `list` vira `tuple` (também recursiva).

    Achado de uma rodada de revisão em cima do fix anterior (`_snapshot_json`
    fazendo só uma cópia INDEPENDENTE, ainda mutável): copiar o dict do
    chamador resolve mutar o ORIGINAL depois de guardado, mas não impede
    mutar a cópia JÁ GUARDADA através da própria referência devolvida por
    `entrada.resultado`/`checkpoint.dados` -- `frozen=True` no dataclass só
    impede reatribuir o ATRIBUTO (`entrada.resultado = outra_coisa` levanta
    `FrozenInstanceError`), nunca protegeu o CONTEÚDO mutável apontado por
    ele (`entrada.resultado["x"] = ...` sempre funcionou, mesmo com o
    snapshot). `MappingProxyType`/`tuple` fecham essa segunda porta: não há
    operação pública em nenhum dos dois tipos que mute o conteúdo.

    Efeito colateral desejado (não seria suficiente sozinho, mas reforça):
    também neutraliza `copy.copy()` num `Checkpoint`/`LedgerEntry` (que
    contorna `__post_init__` e compartilharia o mesmo objeto `dados`/
    `resultado` com o original) -- como esse objeto compartilhado agora é
    imutável, mesmo um `copy.copy` não abre uma via de mutação.

    RISCO ACEITO, documentado (não corrigido -- mesma família do risco já
    aceito para `int`/`float` em `hash_canonico`): como `list` E `tuple`
    convergem para `tuple` aqui (JSON não distingue os dois -- é sempre um
    "array"), um `resultado`/`dados` reenviado com `[10, 20]` (list) depois
    de já ter sido registrado como `(10, 20)` (tuple), ou vice-versa, é
    tratado como o MESMO valor por `_mesmo_valor_canonico` -- não é uma
    regressão desta função: `hash_canonico`/`_mesmo_valor_canonico` já
    tratavam list e tuple como equivalentes para fins de comparação desde a
    1a rodada de revisão (`_canonicalizar_chaves` sempre convertia os dois
    para o mesmo formato antes de comparar); esta função só faz o valor
    GUARDADO também refletir essa mesma canonicalização, em vez de manter o
    tipo Python original do chamador -- e um `array` JSON de verdade
    (Firestore incluído) não distingue os dois de qualquer forma."""
    if isinstance(valor, dict):
        return MappingProxyType(
            {chave: _congelar_profundamente(item) for chave, item in valor.items()}
        )
    if isinstance(valor, list):
        return tuple(_congelar_profundamente(item) for item in valor)
    return valor


def _snapshot_json(valor: Any) -> Any:
    """Devolve uma cópia RECURSIVAMENTE IMUTÁVEL de `valor`, livre de
    qualquer referência mutável compartilhada com o objeto original --
    achado do Codex (P2) na PR #328: sem isto, `Checkpoint.dados`/
    `LedgerEntry.resultado` guardavam o objeto MUTÁVEL do chamador por
    referência (ex.: um `dict`); mutar esse dict original DEPOIS de
    guardado mudava o conteúdo do checkpoint/resultado "imutável" sem
    passar por `adicionar_checkpoint`/`registrar_resultado` nem por nenhuma
    validação -- quebra a garantia de nunca sobrescrever (item 10) na
    prática, apesar do dataclass ser `frozen`. `frozen` só impede reatribuir
    o ATRIBUTO; não protege o CONTEÚDO de um atributo mutável -- por isso o
    resultado desta função é congelado recursivamente (`_congelar_profundamente`),
    não só copiado: uma cópia mutável ainda deixaria `entrada.resultado["x"]
    = ...` funcionar direto na própria entrada já guardada.

    Implementado como round-trip por `_serializar_canonico`/`json.loads`
    seguido de `_congelar_profundamente`: além de produzir uma cópia
    profunda genuína (sem nenhum objeto compartilhado com `valor`), isto
    valida serializabilidade JSON e aplica a MESMA canonicalização de chave
    (`_chave_no_espirito_json`) usada em todo o resto do módulo --
    consequência deliberada, não efeito colateral acidental: também fecha o
    achado do Codex (P2) de que um `resultado` não-serializável (ex.:
    `datetime`) era aceito silenciosamente na PRIMEIRA chamada de
    `registrar_resultado` (que não serializava nada) e só quebrava com
    `TypeError` numa REENTREGA (quando a comparação via
    `_serializar_canonico` rodava pela primeira vez) -- agora falha
    imediatamente na primeira chamada, consistente com o resto do módulo."""
    return _congelar_profundamente(json.loads(_serializar_canonico(valor)))


def _normalizar_idempotency_key(idempotency_key: str) -> str:
    chave_limpa = str(idempotency_key or "").strip()
    if not chave_limpa:
        raise ValueError("idempotency_key é obrigatória (não pode ser vazia).")
    return chave_limpa


@dataclass(frozen=True)
class Checkpoint:
    """Um ponto de retomada dentro de uma operação -- seção 4.5, item 8:
    "após queda, recuperar checkpoint."

    `sequencia` é 1-indexada e estritamente crescente dentro da mesma
    operação (ver `adicionar_checkpoint`), mesmo depois de checkpoints
    antigos serem descartados por `MAX_CHECKPOINTS_POR_OPERACAO` -- assim um
    executor que retoma sempre sabe se está vendo o checkpoint mais recente
    de verdade, e não um buraco na numeração é confundido com progresso
    perdido.

    `dados` aceita um `dict` na construção, mas `__post_init__` substitui o
    valor guardado por uma versão RECURSIVAMENTE imutável
    (`MappingProxyType`/`tuple` -- ver `_snapshot_json`/`_congelar_profundamente`):
    `Checkpoint(...).dados` nunca é o mesmo objeto `dict` passado pelo
    chamador, e não pode ser mutado depois (`TypeError` numa tentativa de
    `dados["x"] = ...`). Compara igual a um `dict`/`list` equivalente
    (`MappingProxyType`/`tuple` implementam `__eq__` contra o tipo mutável
    correspondente), então testes que comparam `checkpoint.dados ==
    {"algo": 1}` continuam funcionando normalmente."""

    sequencia: int
    dados: dict[str, Any]
    criado_em: datetime

    def __post_init__(self) -> None:
        _exigir_tz_aware(self.criado_em, "criado_em")
        if self.sequencia < 1:
            raise ValueError("sequencia de checkpoint deve ser >= 1 (1-indexada).")
        # Snapshot (congelado -- ver docstring de `_snapshot_json`) ANTES de
        # medir o tamanho, para que o tamanho medido seja o da forma
        # canônica de verdade que fica retida (object.__setattr__ porque a
        # dataclass é frozen). `_serializar_canonico`, não `json.dumps` cru
        # -- `dados_snapshot` pode conter `MappingProxyType`/`tuple`
        # (resultado do congelamento), que `json.dumps` não serializa
        # diretamente; `_serializar_canonico` trata `Mapping` de forma
        # genérica (ver docstring de `_canonicalizar_chaves`).
        dados_snapshot = _snapshot_json(self.dados)
        object.__setattr__(self, "dados", dados_snapshot)
        tamanho_bytes = len(_serializar_canonico(dados_snapshot).encode("utf-8"))
        if tamanho_bytes > MAX_CHECKPOINT_BYTES:
            raise CheckpointMuitoGrande(tamanho_bytes, MAX_CHECKPOINT_BYTES)


@dataclass(frozen=True)
class LedgerEntry:
    """Entrada do ledger de uma operação -- seção 4.5, item 6.

    Imutável, como `Lease` em `autonomy/requests.py`: toda função que
    "atualiza" uma entrada (`adicionar_checkpoint`, `registrar_resultado`)
    devolve uma instância NOVA em vez de mutar esta -- quem persiste decide
    quando/como sobrescrever o documento.

    `resultado_registrado_em` é o indicador de "já tem resultado observado"
    (item 9), não `resultado is not None` -- um resultado observado
    legítimo pode ser `None` (ex.: operação que não produz valor de
    retorno), então usar o próprio valor como sentinela seria ambíguo.

    `resultado`, se for um `dict`/`list`, também vira RECURSIVAMENTE
    imutável depois de `__post_init__` (mesmo mecanismo de `Checkpoint.dados`
    -- ver sua docstring)."""

    idempotency_key: str
    payload_hash: str
    criado_em: datetime
    checkpoints: tuple[Checkpoint, ...] = ()
    resultado: Any = None
    resultado_registrado_em: datetime | None = None

    def __post_init__(self) -> None:
        _exigir_tz_aware(self.criado_em, "criado_em")
        if self.resultado_registrado_em is not None:
            _exigir_tz_aware(self.resultado_registrado_em, "resultado_registrado_em")
        # Snapshot de `resultado` -- ver docstring de `_snapshot_json`. Roda
        # incondicionalmente (mesmo quando `resultado` é o default `None`,
        # caso em que é um no-op) porque `dataclasses.replace` reconstrói a
        # instância inteira, então este é o único ponto por onde TODO
        # `resultado` novo passa, venha de `registrar_resultado` ou de uma
        # construção direta de `LedgerEntry`.
        object.__setattr__(self, "resultado", _snapshot_json(self.resultado))


def criar_entrada(
    idempotency_key: str,
    payload: dict[str, Any],
    agora: datetime | None = None,
) -> LedgerEntry:
    """Cria uma entrada nova de ledger para `idempotency_key`/`payload`.

    Não verifica se já existe uma entrada -- isso é responsabilidade de
    `criar_ou_reusar_entrada`, que é a função que o wiring deve chamar na
    prática (esta existe separada para o caso já confirmado de "não existe
    entrada ainda", e para os testes)."""
    chave_limpa = _normalizar_idempotency_key(idempotency_key)
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    agora_resolvido = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return LedgerEntry(
        idempotency_key=chave_limpa,
        payload_hash=hash_canonico(payload),
        criado_em=agora_resolvido,
    )


def criar_ou_reusar_entrada(
    idempotency_key: str,
    payload: dict[str, Any],
    entrada_existente: LedgerEntry | None,
    agora: datetime | None = None,
) -> LedgerEntry:
    """Seção 4.5, item 6: "antes de qualquer efeito, criar/reusar
    operation_ledger com chave única e hash canônico."

    - `entrada_existente is None` -> cria e devolve uma entrada nova.
    - `entrada_existente` presente e mesmo hash de payload -> devolve a
      MESMA entrada (reuso -- nenhum campo é alterado, é responsabilidade
      de quem chama não regravar o documento neste caso).
    - `entrada_existente` presente com hash de payload DIFERENTE -> levanta
      `ConflitoIdempotencia` (item 10) -- nunca sobrescreve.

    `entrada_existente.idempotency_key` que não bate com `idempotency_key`
    é erro de programação de quem chama (leu a entrada errada do
    armazenamento) -- levanta `ValueError`, não é tratado como conflito de
    payload.

    `agora`, se fornecido, é validado (tz-aware) logo no início, ANTES de
    qualquer branch -- achado da 2a rodada de revisão adversarial (P04
    sub-entrega 2/N): antes desta checagem, só o branch
    `entrada_existente is None` validava `agora` (delegando para
    `criar_entrada`); os branches de reuso e de conflito aceitavam um
    `agora` naive silenciosamente, a mesma classe de bug que a 1a rodada já
    havia corrigido em `registrar_resultado`, só que nesta função irmã de
    forma idêntica."""
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    chave_limpa = _normalizar_idempotency_key(idempotency_key)
    if entrada_existente is None:
        return criar_entrada(chave_limpa, payload, agora=agora)
    if entrada_existente.idempotency_key != chave_limpa:
        raise ValueError(
            f"entrada_existente pertence a idempotency_key "
            f"{entrada_existente.idempotency_key!r}, não a {chave_limpa!r} -- "
            "quem chama passou a entrada errada."
        )
    hash_novo = hash_canonico(payload)
    if hash_novo != entrada_existente.payload_hash:
        raise ConflitoIdempotencia(chave_limpa, entrada_existente.payload_hash, hash_novo)
    return entrada_existente


class ReentregaStatus(str, Enum):
    """Seção 4.5, item 9: os dois desfechos possíveis de uma reentrega."""

    TRABALHO_EM_CURSO = "trabalho_em_curso"
    RESULTADO_OBSERVADO = "resultado_observado"


@dataclass(frozen=True)
class ReentregaResultado:
    status: ReentregaStatus
    resultado: Any
    ultimo_checkpoint: Checkpoint | None


def consultar_reentrega(entrada: LedgerEntry) -> ReentregaResultado:
    """Seção 4.5, item 9: "reentrega do mesmo pedido retorna trabalho em
    curso ou resultado já observado."

    Não decide nada sozinha sobre o que fazer com o resultado -- só expõe o
    que o ledger já sabe. `resultado` só é significativo quando
    `status == RESULTADO_OBSERVADO` (pode ser `None` mesmo nesse caso, ver
    docstring de `LedgerEntry`); em `TRABALHO_EM_CURSO` vem sempre `None` e
    deve ser ignorado."""
    ultimo_checkpoint = entrada.checkpoints[-1] if entrada.checkpoints else None
    if entrada.resultado_registrado_em is not None:
        return ReentregaResultado(
            status=ReentregaStatus.RESULTADO_OBSERVADO,
            resultado=entrada.resultado,
            ultimo_checkpoint=ultimo_checkpoint,
        )
    return ReentregaResultado(
        status=ReentregaStatus.TRABALHO_EM_CURSO,
        resultado=None,
        ultimo_checkpoint=ultimo_checkpoint,
    )


def adicionar_checkpoint(
    entrada: LedgerEntry,
    dados: dict[str, Any],
    agora: datetime | None = None,
) -> LedgerEntry:
    """Acrescenta um checkpoint a `entrada`, devolvendo uma `LedgerEntry`
    nova (imutabilidade -- ver docstring de `LedgerEntry`).

    Levanta `CheckpointMuitoGrande` se `dados` excederem
    `MAX_CHECKPOINT_BYTES` (via `Checkpoint.__post_init__`) -- a entrada
    original não é alterada nesse caso (a construção do `Checkpoint` falha
    antes de qualquer `dataclasses.replace`).

    Reentrega do MESMO checkpoint (achado da 1a rodada de revisão
    adversarial, P04 sub-entrega 2/N): se `dados` for igual (por
    `_mesmo_valor_canonico`) ao checkpoint mais recente já registrado, esta
    função é um no-op e devolve `entrada` sem alteração -- sem isso, um
    heartbeat que reenvia defensivamente o último checkpoint (cenário normal
    de reentrega, o mesmo que o item 9 existe para cobrir) consumia um slot
    de `MAX_CHECKPOINTS_POR_OPERACAO` a cada reenvio e podia fazer o
    descarte FIFO derrubar checkpoints antigos genuinamente distintos só
    para abrir espaço para duplicatas do mais recente -- o oposto do que a
    retenção deveria proteger. Só o ÚLTIMO checkpoint é comparado (não o
    histórico inteiro): um checkpoint igual a um anterior mas diferente do
    mais recente representa progresso que regrediu, não uma reentrega, e é
    acrescentado normalmente.

    Uma operação com resultado já registrado é terminal para efeito de
    checkpoint -- levanta `ValueError` (checkpoint existe para permitir
    retomada de trabalho EM CURSO; depois de concluída, não há mais o que
    retomar)."""
    if entrada.resultado_registrado_em is not None:
        raise ValueError(
            f"operação '{entrada.idempotency_key}' já tem resultado registrado "
            f"em {entrada.resultado_registrado_em.isoformat()} -- não adiciona "
            "checkpoint novo em operação concluída."
        )
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    if entrada.checkpoints and _mesmo_valor_canonico(entrada.checkpoints[-1].dados, dados):
        return entrada
    agora_resolvido = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    proxima_sequencia = entrada.checkpoints[-1].sequencia + 1 if entrada.checkpoints else 1
    novo_checkpoint = Checkpoint(sequencia=proxima_sequencia, dados=dados, criado_em=agora_resolvido)
    checkpoints_atualizados = entrada.checkpoints + (novo_checkpoint,)
    if len(checkpoints_atualizados) > MAX_CHECKPOINTS_POR_OPERACAO:
        checkpoints_atualizados = checkpoints_atualizados[-MAX_CHECKPOINTS_POR_OPERACAO:]
    checkpoints_atualizados = _aplicar_orcamento_cumulativo(checkpoints_atualizados)
    return dataclasses.replace(entrada, checkpoints=checkpoints_atualizados)


def _tamanho_serializado_bytes(dados: dict[str, Any]) -> int:
    # `_serializar_canonico`, não `json.dumps` cru -- `dados` aqui é sempre
    # `Checkpoint.dados` já congelado (`MappingProxyType`/`tuple`), que
    # `json.dumps` não sabe serializar diretamente (ver docstring de
    # `_canonicalizar_chaves`).
    return len(_serializar_canonico(dados).encode("utf-8"))


def _aplicar_orcamento_cumulativo(
    checkpoints: tuple[Checkpoint, ...],
) -> tuple[Checkpoint, ...]:
    """Descarta o(s) checkpoint(s) mais antigo(s) (FIFO) até que o total
    somado caiba em `MAX_CHECKPOINTS_BYTES_TOTAL` -- achado do Codex (P2) na
    PR #328: `MAX_CHECKPOINTS_POR_OPERACAO` (contagem) sozinho não impede
    que os checkpoints retidos, somados, excedam o limite de 1MiB de um
    documento Firestore (20 checkpoints de até 64KiB cada somam até
    1.310.720 bytes). Mantém pelo menos 1 checkpoint (o mais recente) mesmo
    que ele sozinho exceda o orçamento -- não pode acontecer na prática
    (`MAX_CHECKPOINT_BYTES` já é bem menor que `MAX_CHECKPOINTS_BYTES_TOTAL`
    e é aplicado por `Checkpoint.__post_init__` a cada checkpoint
    individual), mas a função não assume essa invariante de fora."""
    checkpoints_restantes = list(checkpoints)
    total_bytes = sum(_tamanho_serializado_bytes(c.dados) for c in checkpoints_restantes)
    while total_bytes > MAX_CHECKPOINTS_BYTES_TOTAL and len(checkpoints_restantes) > 1:
        removido = checkpoints_restantes.pop(0)
        total_bytes -= _tamanho_serializado_bytes(removido.dados)
    return tuple(checkpoints_restantes)


def registrar_resultado(
    entrada: LedgerEntry,
    resultado: Any,
    agora: datetime | None = None,
) -> LedgerEntry:
    """Registra o resultado observado de uma operação -- terminal para o
    ledger (seção 4.5, item 9: é o que uma reentrega passa a devolver).

    Idempotente por natureza (não por acidente): chamar de novo com
    EXATAMENTE o mesmo `resultado` (por `_mesmo_valor_canonico`, não `==` do
    Python -- achado da 1a rodada de revisão adversarial, P04 sub-entrega
    2/N: `==` faz `float("nan") != float("nan")`, então um resultado com
    NaN reenviado IDÊNTICO seria tratado como conflito em vez do no-op que
    este parágrafo promete; `==` também trata `True` e `1` como iguais,
    inconsistente com `hash_canonico` tratando os dois como payloads
    diferentes) é um no-op seguro e devolve `entrada` sem alteração -- é
    exatamente o caso de um executor que reprocessa a própria conclusão
    depois de uma reentrega (item 9). Chamar com um `resultado` DIFERENTE
    depois de já registrado é erro de programação de quem chama (duas
    conclusões diferentes para a mesma operação nunca deveriam acontecer) --
    levanta `ValueError`, nunca sobrescreve (mesmo espírito do item 10,
    aplicado ao resultado em vez do payload de entrada).

    `agora`, se fornecido, é validado (tz-aware) mesmo no caminho de no-op
    idempotente -- achado da mesma rodada: validar ANTES da checagem de
    "já registrado" evita que o caminho de no-op mascare um `agora` naive
    que teria sido rejeitado numa chamada equivalente para uma entrada
    ainda não concluída."""
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    if entrada.resultado_registrado_em is not None:
        if _mesmo_valor_canonico(entrada.resultado, resultado):
            return entrada
        raise ValueError(
            f"operação '{entrada.idempotency_key}' já tem resultado registrado "
            f"em {entrada.resultado_registrado_em.isoformat()}, diferente do "
            "resultado novo -- não sobrescreve."
        )
    agora_resolvido = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return dataclasses.replace(
        entrada,
        resultado=resultado,
        resultado_registrado_em=agora_resolvido,
    )
