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
a espera que ninguém acorda é varrida por `autonomy.sweep.varrer_espera_vencida`;
`acordar_espera_externa` retoma a espera com lease/run novos.
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
from autonomy.requests import (
    DEFAULT_LEASE_SEGUNDOS,
    RequestStatus,
    lease_expirada,
    nova_lease,
    validar_transicao,
)
from autonomy.runner_continuacao import DecisaoContinuacao
from autonomy.runs import (
    AgentRun,
    AgentRunStatus,
    concluir_run as _run_concluir,
    criar_run as _run_criar,
    expirar_por_timeout as _run_expirar_por_timeout,
    marcar_em_andamento as _run_marcar_em_andamento,
    run_esta_ativo,
)

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


def acordar_espera_externa(
    pedido: PedidoDuravel,
    executor_id: str,
    run_id: str,
    agora: datetime,
    duracao_segundos: float = DEFAULT_LEASE_SEGUNDOS,
    por_evento: bool = False,
) -> tuple[PedidoDuravel, AgentRun | None]:
    """Retoma um pedido `AGUARDANDO_EXTERNO` num worker novo (P08, passo 5).

    A espera não segura worker nem lease: ao acordar (horário alcançado, ou
    `por_evento=True` quando a condição externa chegou antes do horário) quem
    acorda não tem o token antigo. Fencing: exige a lease anterior vencida
    (nunca toma uma reserva ainda válida), emite lease NOVA com geração + 1 (o
    token/geração velhos perdem o direito de concluir), fecha o run antigo por
    timeout e abre um run novo já `EM_ANDAMENTO`. Status volta a
    `EM_ANDAMENTO` (transição validada pelo grafo); ledger, tentativas e
    pausas são preservados (a retomada é a mesma tentativa lógica, não conta
    como retentativa). `condicao_espera` e `proximo_tentativa_em` são limpos.

    Devolve `(pedido, run_antigo_fechado)`: o pedido só guarda o run corrente,
    então o wiring deve persistir também o run antigo já fechado por timeout
    (`None` se o pedido não tinha run), ou ele ficaria ativo para sempre (A02).

    Função pura: dois despertares concorrentes (ou um despertar e o sweep) sobre o
    mesmo snapshot geram ambos geração + 1; a exclusão mútua é do wiring, com
    compare-and-swap da escrita em `generation` e `status` lidos.

    Sem `por_evento`, acordar antes de `proximo_tentativa_em` levanta
    `LeaseInvalida`; lease ainda válida também (o evento pode ser reentregue
    depois que ela vencer)."""
    if not isinstance(pedido, PedidoDuravel):
        raise ValueError("pedido deve ser PedidoDuravel.")
    if not isinstance(agora, datetime) or agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError("agora deve ser datetime com fuso.")
    if not isinstance(por_evento, bool):
        raise ValueError("por_evento deve ser bool.")
    agora = agora.astimezone(timezone.utc)
    if pedido.status != RequestStatus.AGUARDANDO_EXTERNO:
        raise ValueError(
            f"pedido '{pedido.request_id}' está em '{pedido.status.value}', não 'aguardando_externo'."
        )
    ok, motivo = validar_transicao(pedido.status, RequestStatus.EM_ANDAMENTO)
    if not ok:
        raise ValueError(motivo)
    if pedido.lease is None:
        raise LeaseInvalida(f"pedido '{pedido.request_id}' não tem lease anterior para suceder.")
    if not lease_expirada(pedido.lease, agora=agora):
        raise LeaseInvalida(
            f"lease anterior ainda válida (expira em {pedido.lease.expires_at.isoformat()}) "
            "-- não é possível acordar antes de expirar."
        )
    if (
        not por_evento
        and pedido.proximo_tentativa_em is not None
        and agora < pedido.proximo_tentativa_em
    ):
        raise LeaseInvalida(
            f"pedido '{pedido.request_id}' só acorda em {pedido.proximo_tentativa_em.isoformat()}."
        )
    if pedido.run is not None and str(run_id or "").strip() == pedido.run.run_id:
        raise ValueError("run_id deve ser novo (igual ao do run corrente).")
    lease_nova = nova_lease(
        executor_id, pedido.lease.generation, agora=agora, duracao_segundos=duracao_segundos
    )
    run_antigo = pedido.run
    if run_antigo is not None and run_esta_ativo(run_antigo):
        run_antigo = _run_expirar_por_timeout(run_antigo, lease_expirada=True, agora=agora)
    run_novo = _run_marcar_em_andamento(
        _run_criar(
            run_id=run_id, request_id=pedido.request_id, executor_id=executor_id,
            lease_token=lease_nova.lease_token, generation=lease_nova.generation, agora=agora,
        ),
        lease_nova.lease_token, lease_nova.generation,
    )
    novo = dataclasses.replace(
        pedido, status=RequestStatus.EM_ANDAMENTO, lease=lease_nova, run=run_novo,
        condicao_espera="", proximo_tentativa_em=None,
    )
    return novo, run_antigo
