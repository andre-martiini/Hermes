"""Aplicação da decisão de continuação ao pedido durável (P08, passos 4-7).

Função pura, sem I/O: `autonomy.runner_continuacao.decidir_continuacao`
decide o próximo estado; aqui a decisão é gravada no `PedidoDuravel` sob
fencing (lease/geração) e com a mesma transição validada pelo grafo de
`autonomy.requests`. O wiring persiste o pedido devolvido e enfileira a
continuação em `proximo_tentativa_em`.

- `VERIFICANDO` e `AGUARDANDO_EXTERNO` mantêm lease e run: a tentativa
  segue ativa (o verificador conclui; a espera volta por
  `registrar_progresso`). `AGUARDANDO_EXTERNO` guarda a condição e o horário
  de acordar (`proximo_tentativa_em`, só significativo nesse estado).
- `RETENTATIVA_AGENDADA` encerra a tentativa: run fechado como falha e lease
  liberada (expira em `agora`, mesmo token/geração, para a próxima reserva
  não esbarrar em lease ainda válida). Contadores gravados.
- `FALHA_FINAL` sela o ledger (quando aberto) via
  `registrar_resultado_observado`; sem ledger, só transiciona e fecha o run.

Contadores da decisão nunca regridem em relação ao pedido. Limite conhecido:
lease vencida durante `AGUARDANDO_EXTERNO` não tem saída no sweep/grafo (lacuna
já documentada em `autonomy.sweep`); o wiring deve renovar a lease ao acordar.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

from autonomy.execution import (
    LeaseInvalida,
    PedidoDuravel,
    _fechar_run_se_houver,
    _validar_fencing,
    registrar_resultado_observado,
)
from autonomy.requests import RequestStatus, validar_transicao
from autonomy.runner_continuacao import DecisaoContinuacao
from autonomy.runs import AgentRunStatus, concluir_run as _run_concluir

_ACEITOS = frozenset({
    RequestStatus.VERIFICANDO,
    RequestStatus.AGUARDANDO_EXTERNO,
    RequestStatus.RETENTATIVA_AGENDADA,
    RequestStatus.FALHA_FINAL,
})


def aplicar_decisao_continuacao(
    pedido: PedidoDuravel,
    lease_token: str,
    generation: int,
    decisao: DecisaoContinuacao,
    agora: datetime,
) -> PedidoDuravel:
    if not isinstance(pedido, PedidoDuravel) or not isinstance(decisao, DecisaoContinuacao):
        raise ValueError("pedido e decisao devem ser PedidoDuravel e DecisaoContinuacao.")
    if not isinstance(agora, datetime) or agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError("agora deve ser datetime com fuso.")
    agora = agora.astimezone(timezone.utc)
    novo = decisao.novo_status
    if not isinstance(novo, RequestStatus) or novo not in _ACEITOS:
        raise ValueError(f"decisão com status '{getattr(novo, 'value', novo)}' não é aplicável.")
    for nome in ("tentativas", "pausas"):
        v = getattr(decisao, nome)
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError(f"{nome} deve ser inteiro >= 0")
    if decisao.tentativas < pedido.tentativas or decisao.pausas < pedido.pausas:
        raise ValueError("contadores da decisão não podem regredir em relação ao pedido.")
    if decisao.continuar_em is not None and (
        not isinstance(decisao.continuar_em, datetime)
        or decisao.continuar_em.tzinfo is None
        or decisao.continuar_em.utcoffset() is None
    ):
        raise ValueError("continuar_em deve ser datetime com fuso.")
    if not isinstance(decisao.condicao_espera, str):
        raise ValueError("condicao_espera deve ser texto.")
    _validar_fencing(pedido, lease_token, generation, agora)
    if pedido.status != RequestStatus.EM_ANDAMENTO:
        raise ValueError(
            f"pedido '{pedido.request_id}' está em '{pedido.status.value}'; "
            "a decisão só se aplica a um pedido em_andamento."
        )
    ok, motivo = validar_transicao(pedido.status, novo)
    if not ok:
        raise ValueError(motivo)

    if novo is RequestStatus.FALHA_FINAL:
        base = dataclasses.replace(
            pedido, tentativas=decisao.tentativas, pausas=decisao.pausas,
            proximo_tentativa_em=None, condicao_espera="",
        )
        resultado = {"motivo": decisao.motivo}
        if base.ledger_entry is not None:
            return registrar_resultado_observado(
                base, lease_token, generation, resultado, novo, agora=agora
            )
        run = _fechar_run_se_houver(
            base.run, lease_token, generation, novo, resultado,
            lease_ainda_valida=True, agora=agora,
        )
        return dataclasses.replace(base, status=novo, run=run)

    if novo is RequestStatus.RETENTATIVA_AGENDADA:
        if decisao.continuar_em is None:
            raise ValueError("retentativa_agendada exige continuar_em.")
        run = pedido.run
        if run is not None:
            run = _run_concluir(
                run, lease_token, generation, AgentRunStatus.FALHA,
                lease_ainda_valida=True, resultado={"motivo": decisao.motivo}, agora=agora,
            )
        return dataclasses.replace(
            pedido, status=novo, run=run,
            lease=dataclasses.replace(pedido.lease, expires_at=agora),
            tentativas=decisao.tentativas, pausas=decisao.pausas,
            proximo_tentativa_em=decisao.continuar_em, condicao_espera="",
        )

    if novo is RequestStatus.AGUARDANDO_EXTERNO:
        if not decisao.condicao_espera.strip():
            raise ValueError("aguardando_externo exige condicao_espera.")
        return dataclasses.replace(
            pedido, status=novo, tentativas=decisao.tentativas, pausas=decisao.pausas,
            proximo_tentativa_em=decisao.continuar_em, condicao_espera=decisao.condicao_espera,
        )

    # VERIFICANDO: tentativa segue ativa, lease e run preservados.
    return dataclasses.replace(
        pedido, status=novo, tentativas=decisao.tentativas, pausas=decisao.pausas,
        proximo_tentativa_em=None, condicao_espera="",
    )
