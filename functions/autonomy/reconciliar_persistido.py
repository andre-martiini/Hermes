"""Reconciliação persistida de um pedido `RESULTADO_DESCONHECIDO` (P08, passo 5: wiring).

Liga `reconciliar_resultado_desconhecido` (pura) ao repositório transacional,
no molde de `acordar_persistido`: lê o pedido, reconcilia e grava o pedido junto
com o run antigo, se ainda ativo e fechado por timeout
(`runs_encerrados/{run_id}`), no mesmo read-modify-write. `agora` é resolvido
uma vez fora da transação. Pedido que a função pura recusa (lease válida,
status errado, teto de tentativas) sobe ValueError/LeaseInvalida sem gravar.
Nada chama este módulo em produção (shadow/off).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from autonomy.acordar_persistido import ResultadoDespertar
from autonomy.pedido_repositorio import _validar_id_documento, atualizar_pedido
from autonomy.requests import DEFAULT_LEASE_SEGUNDOS, _exigir_tz_aware
from autonomy.runner_aplicacao import reconciliar_resultado_desconhecido
from autonomy.runs import AgentRun


def reconciliar_pedido(
    db: Any,
    request_id: str,
    efeito_ocorreu: bool,
    agora: datetime | None = None,
    executor_id: str = "",
    run_id: str = "",
    continuar_em: datetime | None = None,
    duracao_segundos: float = DEFAULT_LEASE_SEGUNDOS,
) -> ResultadoDespertar:
    if efeito_ocorreu is True:
        _validar_id_documento(run_id, "run_id")  # falha antes de gravar, não ao arquivar depois
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    agora_resolvido = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ultimo: dict[str, AgentRun | None] = {"antigo": None}

    def _transformar(atual):
        novo, antigo = reconciliar_resultado_desconhecido(
            atual, efeito_ocorreu, agora_resolvido, executor_id=executor_id, run_id=run_id,
            continuar_em=continuar_em, duracao_segundos=duracao_segundos,
        )
        ultimo["antigo"] = antigo
        return novo

    pedido = atualizar_pedido(db, request_id, _transformar, run_encerrado=lambda: ultimo["antigo"])
    return ResultadoDespertar(pedido=pedido, run_antigo=ultimo["antigo"])
