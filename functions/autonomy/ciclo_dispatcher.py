"""Ciclo do dispatcher do runner (P08, passos 3, 4 e 11: orquestra config + orçamento + decisão).

Uma passada: lê a config (`ler_config_dispatcher`); em `off` não toca em pedidos. Senão lê UMA página
de pedidos despacháveis (PENDENTE / RETENTATIVA_AGENDADA, em ordem de id), decide com `decidir_lote`
e executa: em `shadow` só devolve o que SERIA enfileirado; em `ativo` baixa 1 do orçamento
(`consumir_orcamento`, ANTES de enfileirar; estornado por `devolver_orcamento` só quando o enfileirador recusa por duplicata) e chama o `enfileirar(nome, payload)` injetado (o Cloud Tasks
real fica para o wiring). Sem orçamento a passada para de enfileirar. `JaDespachado` (ALREADY_EXISTS) conta
como já despachado. Qualquer outra falha do enfileirador
vira item de `erros` sem estorno (resultado ambíguo: o orçamento fica gasto, lado seguro) e sem derrubar os demais. Pedido ilegível vira erro, não interrompe. Nada chama este
módulo em produção (shadow/off); agendar a passada fica para depois; lê até MAX_PAGINAS páginas de `limite`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from autonomy.config_dispatcher import consumir_orcamento, devolver_orcamento, ler_config_dispatcher
from autonomy.dispatcher import AcaoDespacho, ModoDispatcher, decidir_lote
from autonomy.pedido_repositorio import COLECAO_PEDIDOS, ler_pedido
from autonomy.requests import RequestStatus, _exigir_tz_aware

STATUS_DESPACHAVEIS = (RequestStatus.PENDENTE, RequestStatus.RETENTATIVA_AGENDADA)
LIMITE_PADRAO = 50
MAX_PAGINAS = 5


class JaDespachado(Exception):
    """O enfileirador recusou o nome por duplicata (ALREADY_EXISTS): despacho já feito."""


@dataclass(frozen=True)
class ResultadoCiclo:
    modo: ModoDispatcher
    motivo_config: str
    candidatos: int
    sombra: tuple[tuple[str, str], ...]  # (request_id, nome_tarefa) que seriam enfileirados
    enfileirados: tuple[tuple[str, str], ...]
    ja_despachados: tuple[str, ...]
    sem_orcamento: bool
    erros: tuple[tuple[str, str], ...]


def _vazio(cfg) -> ResultadoCiclo:
    return ResultadoCiclo(cfg.modo, cfg.motivo, 0, (), (), (), False, ())


def _ids_despachaveis(db: Any, limite: int) -> list[str]:
    """Até MAX_PAGINAS páginas (cursor por id): bloqueadores com id baixo não escondem os demais."""
    ids: list[str] = []
    apos = None
    for _ in range(MAX_PAGINAS):
        consulta = (
            db.collection(COLECAO_PEDIDOS)
            .where("pedido.status", "in", [s.value for s in STATUS_DESPACHAVEIS])
            .order_by("__name__")
        )
        if apos is not None:
            consulta = consulta.start_after({"__name__": apos})
        docs = list(consulta.limit(limite).stream())
        ids.extend(d.id for d in docs)
        if len(docs) < limite:
            break
        apos = docs[-1].id
    return ids


def executar_ciclo(
    db: Any,
    enfileirar: Callable[[str, dict[str, str]], None],
    agora: datetime | None = None,
    limite: int = LIMITE_PADRAO,
) -> ResultadoCiclo:
    if isinstance(limite, bool) or not isinstance(limite, int) or limite < 1:
        raise ValueError("limite deve ser inteiro >= 1.")
    if agora is not None and not isinstance(agora, datetime):
        raise ValueError("agora deve ser datetime com fuso.")
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    agora_r = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cfg = ler_config_dispatcher(db)
    if cfg.modo is ModoDispatcher.OFF:
        return _vazio(cfg)
    erros: list[tuple[str, str]] = []
    pedidos = []
    try:
        ids = _ids_despachaveis(db, limite)
    except Exception as exc:  # consulta falhou: nada é despachado, anomalia visível
        return ResultadoCiclo(
            cfg.modo, cfg.motivo, 0, (), (), (), False, (("consulta", f"{type(exc).__name__}: {exc}"),)
        )
    for rid in ids:
        try:
            p = ler_pedido(db, rid)
        except Exception as exc:  # pedido ilegível: anomalia visível, não interrompe
            erros.append((rid, f"{type(exc).__name__}: {exc}"))
            continue
        if p is not None:
            pedidos.append(p)
    decisoes = decidir_lote(pedidos, cfg.modo, agora_r, cfg.despachos_restantes)
    sombra: list[tuple[str, str]] = []
    feitos: list[tuple[str, str]] = []
    ja: list[str] = []
    sem_orc = False
    for p, d in zip(pedidos, decisoes):
        if d.acao is AcaoDespacho.REGISTRAR_SOMBRA:
            sombra.append((p.request_id, d.nome_tarefa))
        elif d.acao is AcaoDespacho.ENFILEIRAR:
            if sem_orc:
                continue
            if consumir_orcamento(db, 1) != 1:
                sem_orc = True  # saldo real acabou ou não confirmou a baixa: para de enfileirar
                continue
            try:
                enfileirar(d.nome_tarefa, dict(d.payload))
            except JaDespachado:
                devolver_orcamento(db, 1)  # nada novo foi despachado: não drena o saldo a cada passada
                ja.append(p.request_id)
            except Exception as exc:  # ambíguo (a tarefa pode ter sido criada): orçamento fica gasto
                erros.append((p.request_id, f"{type(exc).__name__}: {exc}"))
            else:
                feitos.append((p.request_id, d.nome_tarefa))
    return ResultadoCiclo(
        cfg.modo, cfg.motivo, len(pedidos), tuple(sombra), tuple(feitos), tuple(ja), sem_orc, tuple(erros)
    )
