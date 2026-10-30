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
MAX_PAGINAS_PADRAO = 10


@dataclass(frozen=True)
class ResultadoLote:
    """`varridos`: (request_id, acao) dos pedidos gravados; `erros`:
    (request_id, "Tipo: mensagem"); `candidatos`: quantos a consulta trouxe;
    `truncado`: True se o teto de páginas foi atingido com a última página cheia (pode haver mais pedidos por ler; falso positivo quando o total é exatamente limite*max_paginas).
    `proximo_cursor`: id do último pedido lido quando `truncado` (senão None); passar como
    `apos_id` na passada seguinte para continuar dali em vez de reler o mesmo prefixo
    (a próxima passada começa de novo do início: aumentar o teto ou a cadência)."""

    candidatos: int
    truncado: bool
    proximo_cursor: str | None
    varridos: tuple[tuple[str, str], ...]
    diagnosticos: tuple[DiagnosticoPedido, ...]
    erros: tuple[tuple[str, str], ...]


def _validar_inteiro_positivo(valor: Any, nome: str) -> None:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
        raise ValueError(f"{nome} deve ser inteiro >= 1.")


def _pagina(db: Any, limite: int, apos: str | None = None) -> list[Any]:
    """Uma página de documentos em status varrível, em ordem de id. Sem
    ordenação+cursor um `limit` devolveria sempre os mesmos documentos (pedidos
    com lease válida ou com erro permanente ocupariam a página para sempre)."""
    consulta = (
        db.collection(COLECAO_PEDIDOS)
        .where("pedido.status", "in", [s.value for s in STATUS_VARRIVEIS])
        .order_by("__name__")
    )
    if apos is not None:
        consulta = consulta.start_after({"__name__": apos})
    return list(consulta.limit(limite).stream())


def listar_candidatos(db: Any, limite: int = LIMITE_PADRAO) -> list[str]:
    """Ids (primeira página, em ordem de id) em status varrível."""
    _validar_inteiro_positivo(limite, "limite")
    return [doc.id for doc in _pagina(db, limite)]


def varrer_candidatos(
    db: Any,
    agora: datetime | None = None,
    limite: int = LIMITE_PADRAO,
    max_tentativas: int = DEFAULT_MAX_TENTATIVAS,
    max_paginas: int = MAX_PAGINAS_PADRAO,
    apos_id: str | None = None,
) -> ResultadoLote:
    """Uma passada do sweep, paginando por cursor até esgotar os candidatos ou
    atingir `max_paginas` (`truncado`; continue com `apos_id=proximo_cursor`). `agora` é resolvido uma vez."""
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    _validar_inteiro_positivo(limite, "limite")
    _validar_inteiro_positivo(max_paginas, "max_paginas")
    _validar_inteiro_positivo(max_tentativas, "max_tentativas")
    if apos_id is not None and (not isinstance(apos_id, str) or not apos_id):
        raise ValueError("apos_id deve ser str não vazia ou None.")
    agora_resolvido = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    varridos: list[tuple[str, str]] = []
    diagnosticos: list[DiagnosticoPedido] = []
    erros: list[tuple[str, str]] = []
    total = 0
    apos = apos_id
    truncado = False
    for pagina_n in range(max_paginas):
        docs = _pagina(db, limite, apos)
        total += len(docs)
        for doc in docs:
            request_id = doc.id
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
        if len(docs) < limite:
            break
        apos = docs[-1].id
        if pagina_n == max_paginas - 1:
            truncado = True
    return ResultadoLote(total, truncado, apos if truncado else None, tuple(varridos), tuple(diagnosticos), tuple(erros))
