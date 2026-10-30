"""Sweep em lote dos pedidos duráveis (P08, passo 4: wiring de persistência).

Lista os candidatos à varredura (consulta por status no Firestore) e chama
`varrer_pedido` em cada um, isolando falhas: um pedido corrompido ou incoerente
vira um item de `erros` e não impede a varredura dos demais. A consulta é só um
pré-filtro por status (a decisão fina de lease/horário continua em
`decidir_varredura`, pura). Persistir a fila de diagnóstico e agendar a
execução periódica ficam para a sub-entrega seguinte; nada chama este módulo
em produção (shadow/off).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from autonomy.pedido_repositorio import COLECAO_PEDIDOS, PedidoNaoEncontrado
from autonomy.requests import DEFAULT_MAX_TENTATIVAS, RequestStatus, _exigir_tz_aware
from autonomy.sweep import DiagnosticoPedido
from autonomy.sweep_persistido import varrer_pedido

#: Únicos status que `decidir_varredura` pode agir (o resto devolve None).
STATUS_VARRIVEIS = (
    RequestStatus.RESERVADO,
    RequestStatus.EM_ANDAMENTO,
    RequestStatus.RETENTATIVA_AGENDADA,
    RequestStatus.AGUARDANDO_EXTERNO,
    RequestStatus.VERIFICANDO,
)
LIMITE_PADRAO = 100


@dataclass(frozen=True)
class ResultadoLote:
    """`varridos`: (request_id, acao) dos pedidos gravados; `erros`:
    (request_id, "Tipo: mensagem"); `candidatos`: quantos a consulta trouxe."""

    candidatos: int
    varridos: tuple[tuple[str, str], ...]
    diagnosticos: tuple[DiagnosticoPedido, ...]
    erros: tuple[tuple[str, str], ...]


def listar_candidatos(db: Any, limite: int = LIMITE_PADRAO) -> list[str]:
    """Ids (ordenados) dos pedidos em status varrível, no máximo `limite`."""
    if isinstance(limite, bool) or not isinstance(limite, int) or limite < 1:
        raise ValueError("limite deve ser inteiro >= 1.")
    consulta = (
        db.collection(COLECAO_PEDIDOS)
        .where("pedido.status", "in", [s.value for s in STATUS_VARRIVEIS])
        .limit(limite)
    )
    return sorted(doc.id for doc in consulta.stream())


def varrer_candidatos(
    db: Any,
    agora: datetime | None = None,
    limite: int = LIMITE_PADRAO,
    max_tentativas: int = DEFAULT_MAX_TENTATIVAS,
) -> ResultadoLote:
    """Uma passada do sweep. `agora` é resolvido uma vez para todo o lote."""
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    agora_resolvido = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ids = listar_candidatos(db, limite)
    varridos: list[tuple[str, str]] = []
    diagnosticos: list[DiagnosticoPedido] = []
    erros: list[tuple[str, str]] = []
    for request_id in ids:
        try:
            r = varrer_pedido(db, request_id, agora=agora_resolvido, max_tentativas=max_tentativas)
        except PedidoNaoEncontrado:
            continue  # apagado entre a consulta e a varredura
        except Exception as exc:  # isolamento por pedido: anomalia vira item de erro
            erros.append((request_id, f"{type(exc).__name__}: {exc}"))
            continue
        if r.acao is not None:
            varridos.append((request_id, r.acao))
        if r.diagnostico is not None:
            diagnosticos.append(r.diagnostico)
    return ResultadoLote(len(ids), tuple(varridos), tuple(diagnosticos), tuple(erros))
