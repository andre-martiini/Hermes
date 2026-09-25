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
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
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


def hash_canonico(payload: dict[str, Any]) -> str:
    """Hash SHA-256 determinístico de `payload` -- seção 4.5, item 6:
    "chave única e hash canônico."

    Serialização canônica via `json.dumps(..., sort_keys=True)`: chaves
    ordenadas recursivamente em todos os níveis de aninhamento, sem espaços
    supérfluos (`separators=(",", ":")`), para que o MESMO conteúdo lógico
    sempre produza o MESMO hash independentemente da ordem de inserção das
    chaves em memória. `payload` não-serializável em JSON (ex.: contém um
    objeto arbitrário) levanta `TypeError` -- isso é responsabilidade de
    quem monta o payload (código interno), não um caso a normalizar aqui."""
    serializado = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


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
    perdido."""

    sequencia: int
    dados: dict[str, Any]
    criado_em: datetime

    def __post_init__(self) -> None:
        _exigir_tz_aware(self.criado_em, "criado_em")
        if self.sequencia < 1:
            raise ValueError("sequencia de checkpoint deve ser >= 1 (1-indexada).")
        tamanho_bytes = len(
            json.dumps(self.dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
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
    retorno), então usar o próprio valor como sentinela seria ambíguo."""

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
    payload."""
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
    agora_resolvido = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    proxima_sequencia = entrada.checkpoints[-1].sequencia + 1 if entrada.checkpoints else 1
    novo_checkpoint = Checkpoint(sequencia=proxima_sequencia, dados=dados, criado_em=agora_resolvido)
    checkpoints_atualizados = entrada.checkpoints + (novo_checkpoint,)
    if len(checkpoints_atualizados) > MAX_CHECKPOINTS_POR_OPERACAO:
        checkpoints_atualizados = checkpoints_atualizados[-MAX_CHECKPOINTS_POR_OPERACAO:]
    return dataclasses.replace(entrada, checkpoints=checkpoints_atualizados)


def registrar_resultado(
    entrada: LedgerEntry,
    resultado: Any,
    agora: datetime | None = None,
) -> LedgerEntry:
    """Registra o resultado observado de uma operação -- terminal para o
    ledger (seção 4.5, item 9: é o que uma reentrega passa a devolver).

    Idempotente por natureza (não por acidente): chamar de novo com
    EXATAMENTE o mesmo `resultado` é um no-op seguro e devolve `entrada` sem
    alteração -- é exatamente o caso de um executor que reprocessa a própria
    conclusão depois de uma reentrega (item 9). Chamar com um `resultado`
    DIFERENTE depois de já registrado é erro de programação de quem chama
    (duas conclusões diferentes para a mesma operação nunca deveriam
    acontecer) -- levanta `ValueError`, nunca sobrescreve (mesmo espírito do
    item 10, aplicado ao resultado em vez do payload de entrada)."""
    if entrada.resultado_registrado_em is not None:
        if entrada.resultado == resultado:
            return entrada
        raise ValueError(
            f"operação '{entrada.idempotency_key}' já tem resultado registrado "
            f"em {entrada.resultado_registrado_em.isoformat()}, diferente do "
            "resultado novo -- não sobrescreve."
        )
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    agora_resolvido = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return dataclasses.replace(
        entrada,
        resultado=resultado,
        resultado_registrado_em=agora_resolvido,
    )
