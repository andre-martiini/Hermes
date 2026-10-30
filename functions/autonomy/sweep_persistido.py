"""Sweep persistido de UM pedido durável (P08, passo 4: wiring de persistência).

Liga as funções puras de `autonomy.sweep` ao repositório transacional
(`autonomy.pedido_repositorio.atualizar_pedido`): `varrer_pedido` escolhe a
varredura pelo status do pedido e grava o resultado num único
read-modify-write. A decisão (`decidir_varredura`) é pura e determinística --
`agora` é resolvido UMA vez fora da transação, então uma reexecução por
contenção decide sobre o mesmo instante. Pedido sem nada a varrer não é
escrito. Quem lista os pedidos candidatos (consulta status+lease) e persiste a
fila de diagnóstico fica para a sub-entrega seguinte; nada chama este módulo em
produção (shadow/off).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from autonomy.execution import PedidoDuravel
from autonomy.pedido_repositorio import atualizar_pedido
from autonomy.requests import DEFAULT_MAX_TENTATIVAS, RequestStatus, _exigir_tz_aware, lease_expirada
from autonomy.sweep import (
    DiagnosticoPedido,
    ResultadoSweepLeaseVencida,
    promover_retentativa_pronta,
    varrer_espera_vencida,
    varrer_lease_vencida,
)


@dataclass(frozen=True)
class ResultadoVarredura:
    """`acao` é None quando o pedido não tinha nada a varrer (nada gravado)."""

    pedido: PedidoDuravel
    acao: str | None
    diagnostico: DiagnosticoPedido | None


def decidir_varredura(
    pedido: PedidoDuravel,
    agora: datetime,
    max_tentativas: int = DEFAULT_MAX_TENTATIVAS,
) -> tuple[str, ResultadoSweepLeaseVencida] | None:
    """Pura. None = nada a fazer agora. Estado incoerente (ex.: sem lease em
    RESERVADO/EM_ANDAMENTO, retentativa sem horário) deixa a ValueError do
    sweep subir: anomalia visível, não varredura silenciosa."""
    _exigir_tz_aware(agora, "agora")
    status = pedido.status
    if status in (RequestStatus.RESERVADO, RequestStatus.EM_ANDAMENTO):
        if pedido.lease is not None and not lease_expirada(pedido.lease, agora=agora):
            return None
        return "lease_vencida", varrer_lease_vencida(pedido, agora=agora, max_tentativas=max_tentativas)
    if status == RequestStatus.RETENTATIVA_AGENDADA:
        if pedido.proximo_tentativa_em is not None and agora < pedido.proximo_tentativa_em:
            return None
        novo = promover_retentativa_pronta(pedido, agora=agora)
        return "retentativa_promovida", ResultadoSweepLeaseVencida(pedido=novo, diagnostico=None)
    if status in (RequestStatus.AGUARDANDO_EXTERNO, RequestStatus.VERIFICANDO):
        if pedido.lease is not None and not lease_expirada(pedido.lease, agora=agora):
            return None
        if (
            status == RequestStatus.AGUARDANDO_EXTERNO
            and pedido.proximo_tentativa_em is not None
            and agora < pedido.proximo_tentativa_em
        ):
            return None
        return "espera_vencida", varrer_espera_vencida(pedido, agora=agora)
    return None


def varrer_pedido(
    db: Any,
    request_id: str,
    agora: datetime | None = None,
    max_tentativas: int = DEFAULT_MAX_TENTATIVAS,
) -> ResultadoVarredura:
    """Varre e persiste um pedido. PedidoNaoEncontrado/PedidoCorrompido sobem
    do repositório; o diagnóstico devolvido é o da gravação que valeu."""
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    agora_resolvido = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ultimo: dict[str, Any] = {"acao": None, "diagnostico": None}

    def _transformar(atual: PedidoDuravel) -> PedidoDuravel:
        decisao = decidir_varredura(atual, agora_resolvido, max_tentativas)
        if decisao is None:
            ultimo["acao"], ultimo["diagnostico"] = None, None
            return atual
        acao, resultado = decisao
        ultimo["acao"], ultimo["diagnostico"] = acao, resultado.diagnostico
        return resultado.pedido

    pedido = atualizar_pedido(db, request_id, _transformar)
    return ResultadoVarredura(pedido=pedido, acao=ultimo["acao"], diagnostico=ultimo["diagnostico"])
