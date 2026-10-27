"""Dispatcher do runner (P08 do plano de autonomia, passos 3 e 11).

Função pura: decide, para um pedido durável, se uma tarefa do Cloud Tasks
deve ser enfileirada, apenas registrada em sombra ou nada. SEM I/O, relógio
escondido ou Cloud Tasks; o wiring executa a decisão.

- Modo `OFF` é o padrão e o destino de qualquer valor de configuração
  inválido (fail-closed): nada é despachado nem registrado.
- Modo `SHADOW` calcula a tarefa que SERIA enfileirada (nome e payload) e a
  devolve para registro, sem enfileirar.
- Modo `ATIVO` só enfileira com orçamento de despachos explícito e positivo
  (passo 11: "até orçamento e política estarem definidos"); sem orçamento
  definido, não despacha.
- O payload carrega só o `request_id` (passo 3: o conteúdo é recuperado do
  banco depois de autenticar). O nome da tarefa é determinístico por pedido
  e tentativa, para o Cloud Tasks recusar duplicata do mesmo despacho.
- Elegibilidade espelha `assumir_pedido`: transição válida para `RESERVADO`,
  lease anterior expirada e retentativa só depois de `proximo_tentativa_em`.
- O nome inclui a geração da lease: o caminho RESERVADO -> PENDENTE não
  incrementa `tentativas`, mas a geração sim a cada reserva, então um novo
  despacho não reutiliza o nome de uma tarefa já executada (o Cloud Tasks
  retém nomes por horas). ALREADY_EXISTS no wiring significa mesmo despacho
  duplicado: tratar como "já despachado".
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from autonomy.execution import PedidoDuravel
from autonomy.requests import RequestStatus, lease_expirada, validar_transicao


class ModoDispatcher(str, Enum):
    OFF = "off"
    SHADOW = "shadow"
    ATIVO = "ativo"


class AcaoDespacho(str, Enum):
    NAO_DESPACHAR = "nao_despachar"
    REGISTRAR_SOMBRA = "registrar_sombra"
    ENFILEIRAR = "enfileirar"


@dataclass(frozen=True)
class DecisaoDespacho:
    acao: AcaoDespacho
    motivo: str
    nome_tarefa: str = ""
    payload: tuple[tuple[str, str], ...] = ()


def modo_de_config(valor: object) -> ModoDispatcher:
    """Valor ausente, de tipo errado ou desconhecido vira `OFF`."""
    if isinstance(valor, ModoDispatcher):
        return valor
    if isinstance(valor, str):
        try:
            return ModoDispatcher(valor.strip().lower())
        except ValueError:
            return ModoDispatcher.OFF
    return ModoDispatcher.OFF


def nome_tarefa(request_id: str, tentativas: int, geracao: int = 0) -> str:
    """Nome válido no Cloud Tasks ([A-Za-z0-9_-]), estável por pedido, tentativa e geração
    da reserva (a geração da lease só cresce, então redespachar depois de uma
    reserva liberada nunca reutiliza o nome de uma tarefa já executada)."""
    h = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:32]
    return f"runner-{h}-t{tentativas}-g{geracao}"


def _elegivel(pedido: PedidoDuravel, agora: datetime) -> str:
    """'' se elegível; senão o motivo."""
    try:
        status = RequestStatus(pedido.status)  # str crua do banco também vale (como assumir_pedido)
    except ValueError:
        return "status_nao_despachavel"
    ok, _ = validar_transicao(status, RequestStatus.RESERVADO)
    if not ok:
        return "status_nao_despachavel"
    if pedido.lease is not None and not lease_expirada(pedido.lease, agora=agora):
        return "lease_ativa"
    if (
        status is RequestStatus.RETENTATIVA_AGENDADA
        and pedido.proximo_tentativa_em is not None
        and agora < pedido.proximo_tentativa_em
    ):
        return "retentativa_futura"
    return ""


def decidir_despacho(
    pedido: PedidoDuravel,
    modo: object,
    agora: datetime,
    despachos_restantes: int | None = None,
) -> DecisaoDespacho:
    if not isinstance(pedido, PedidoDuravel):
        raise TypeError("pedido deve ser PedidoDuravel.")
    if not isinstance(agora, datetime) or agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError("agora deve ser datetime com fuso.")
    modo = modo_de_config(modo)
    if modo is ModoDispatcher.OFF:
        return DecisaoDespacho(AcaoDespacho.NAO_DESPACHAR, "dispatcher_desligado")
    if type(pedido.tentativas) is not int:
        return DecisaoDespacho(AcaoDespacho.NAO_DESPACHAR, "tentativas_invalidas")
    motivo = _elegivel(pedido, agora)
    if motivo:
        return DecisaoDespacho(AcaoDespacho.NAO_DESPACHAR, motivo)
    geracao = pedido.lease.generation if pedido.lease is not None else 0
    if type(geracao) is not int or geracao < 0:
        return DecisaoDespacho(AcaoDespacho.NAO_DESPACHAR, "geracao_invalida")
    nome = nome_tarefa(pedido.request_id, pedido.tentativas, geracao)
    payload = (("request_id", pedido.request_id),)
    if modo is ModoDispatcher.SHADOW:
        return DecisaoDespacho(AcaoDespacho.REGISTRAR_SOMBRA, "sombra", nome, payload)
    if isinstance(despachos_restantes, bool) or not isinstance(despachos_restantes, int) or despachos_restantes <= 0:
        return DecisaoDespacho(AcaoDespacho.NAO_DESPACHAR, "sem_orcamento")
    return DecisaoDespacho(AcaoDespacho.ENFILEIRAR, "elegivel", nome, payload)


def decidir_lote(
    pedidos: list[PedidoDuravel],
    modo: object,
    agora: datetime,
    despachos_restantes: int | None = None,
) -> list[DecisaoDespacho]:
    """Uma decisão por pedido, em ordem; cada ENFILEIRAR consome 1 do orçamento."""
    saldo = despachos_restantes
    saidas: list[DecisaoDespacho] = []
    vistos: set[str] = set()
    for p in pedidos:
        rid = getattr(p, "request_id", None)
        if rid in vistos:  # mesmo pedido repetido não gasta orçamento duas vezes
            saidas.append(DecisaoDespacho(AcaoDespacho.NAO_DESPACHAR, "duplicado_no_lote"))
            continue
        d = decidir_despacho(p, modo, agora, saldo)
        if isinstance(rid, str):
            vistos.add(rid)
        if d.acao is AcaoDespacho.ENFILEIRAR:
            saldo -= 1
        saidas.append(d)
    return saidas
