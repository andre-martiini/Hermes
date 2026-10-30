"""Despertar persistido de um pedido em espera externa (P08, passo 5: wiring).

Liga `acordar_espera_externa` (pura) ao repositório transacional: lê o pedido,
acorda com lease nova (geração + 1) e grava o pedido junto com o run antigo
fechado por timeout (`runs_encerrados/{run_id}`), tudo no mesmo
read-modify-write. `agora` é resolvido uma vez fora da transação. Pedido que a
função pura recusa (lease ainda válida, horário não alcançado, status errado)
sobe ValueError/LeaseInvalida sem gravar. Nada chama este módulo em produção
(shadow/off).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from autonomy.execution import PedidoDuravel
from autonomy.pedido_repositorio import atualizar_pedido
from autonomy.requests import DEFAULT_LEASE_SEGUNDOS, _exigir_tz_aware
from autonomy.runner_aplicacao import acordar_espera_externa
from autonomy.runs import AgentRun


@dataclass(frozen=True)
class ResultadoDespertar:
    pedido: PedidoDuravel
    run_antigo: AgentRun | None


def acordar_pedido(
    db: Any,
    request_id: str,
    executor_id: str,
    run_id: str,
    agora: datetime | None = None,
    duracao_segundos: float = DEFAULT_LEASE_SEGUNDOS,
    por_evento: bool = False,
) -> ResultadoDespertar:
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    agora_resolvido = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ultimo: dict[str, AgentRun | None] = {"antigo": None}

    def _transformar(atual: PedidoDuravel) -> PedidoDuravel:
        novo, antigo = acordar_espera_externa(
            atual, executor_id, run_id, agora_resolvido,
            duracao_segundos=duracao_segundos, por_evento=por_evento,
        )
        ultimo["antigo"] = antigo
        return novo

    pedido = atualizar_pedido(db, request_id, _transformar, run_encerrado=lambda: ultimo["antigo"])
    return ResultadoDespertar(pedido=pedido, run_antigo=ultimo["antigo"])
