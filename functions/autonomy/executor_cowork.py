"""Adaptador de consumo Cowork (P08 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, passo 10: "Criar adaptador de
consumo Cowork com as mesmas reservas; registrar suas capacidades reais. Não
presumir que o runner tem acesso aos conectores da sessão Cowork.").

Lógica pura, sem I/O. Dois tipos de executor disputam o mesmo pedido pela
MESMA reserva (`autonomy.execution.assumir_pedido`: lease, geração, run): o
runner de serviço e a rotina Cowork. Este módulo só acrescenta o que é
específico do passo 10:

- `CapacidadesExecutor`: o que um executor DECLARA saber fazer (conectores,
  ferramentas). Nada é inferido: capacidade não declarada não existe, e o
  runner de serviço nunca herda a do Cowork (nem o contrário).
- `reservar_pedido_para_executor`: recusa a reserva ANTES de tocar o pedido
  quando faltam capacidades exigidas; senão delega a `assumir_pedido`, de modo
  que um segundo executor continua barrado pela lease do primeiro.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from datetime import datetime
from enum import Enum
from typing import Iterable

from autonomy.execution import DEFAULT_LEASE_SEGUNDOS, LeaseInvalida, PedidoDuravel, assumir_pedido
from autonomy.requests import RequestStatus

PREFIXO_COWORK = "cowork:"
MAX_CAPACIDADES = 200
_ID_VALIDO = re.compile(r"[A-Za-z0-9_.:-]{1,100}")
_MAX_LEASE_SEGUNDOS = 86_400


class TipoExecutor(str, Enum):
    RUNNER_SERVICO = "runner_servico"
    COWORK = "cowork"


class DisputaPerdida(Exception):
    """Outro executor já reservou (ou o pedido não está reservável)."""


class CapacidadeInsuficiente(Exception):
    """O executor não declarou todas as capacidades que o pedido exige."""

    def __init__(self, faltantes: tuple[str, ...]) -> None:
        self.faltantes = tuple(faltantes)
        super().__init__("capacidades ausentes: " + ", ".join(faltantes))


def _normalizar(itens: Iterable[str], campo: str) -> frozenset[str]:
    if isinstance(itens, (str, bytes)) or itens is None:
        raise ValueError(f"{campo} deve ser uma coleção de nomes, não um texto único.")
    saida = set()
    for i, item in enumerate(itens):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{campo}[{i}] deve ser um nome não vazio.")
        saida.add(item.strip())
        if len(saida) > MAX_CAPACIDADES:
            raise ValueError(f"{campo} excede {MAX_CAPACIDADES} itens.")
    return frozenset(saida)


@dataclass(frozen=True)
class CapacidadesExecutor:
    executor_id: str
    tipo: TipoExecutor
    capacidades: frozenset[str]

    def __post_init__(self) -> None:
        executor_id = self.executor_id.strip() if isinstance(self.executor_id, str) else ""
        if not executor_id:
            raise ValueError("executor_id é obrigatório.")
        tipo = TipoExecutor(self.tipo)
        if not _ID_VALIDO.fullmatch(executor_id):
            raise ValueError("executor_id deve ter 1-100 caracteres de [A-Za-z0-9_.:-].")
        if tipo is TipoExecutor.COWORK and (
            not executor_id.startswith(PREFIXO_COWORK) or executor_id == PREFIXO_COWORK
        ):
            raise ValueError(f"executor Cowork deve ter id '{PREFIXO_COWORK}<rotina>'.")
        if tipo is TipoExecutor.RUNNER_SERVICO and executor_id.lower().startswith(PREFIXO_COWORK):
            raise ValueError(f"runner de serviço não pode usar o prefixo '{PREFIXO_COWORK}'.")
        object.__setattr__(self, "executor_id", executor_id)
        object.__setattr__(self, "tipo", tipo)
        object.__setattr__(self, "capacidades", _normalizar(self.capacidades, "capacidades"))


def registrar_capacidades_cowork(rotina_id: str, declaradas: Iterable[str]) -> CapacidadesExecutor:
    """Capacidades REAIS da sessão Cowork: só o que ela declarou."""
    rotina = rotina_id.strip() if isinstance(rotina_id, str) else ""
    if not rotina:
        raise ValueError("rotina_id é obrigatório.")
    return CapacidadesExecutor(PREFIXO_COWORK + rotina, TipoExecutor.COWORK, declaradas)


def registrar_capacidades_runner(runner_id: str, declaradas: Iterable[str]) -> CapacidadesExecutor:
    return CapacidadesExecutor(runner_id, TipoExecutor.RUNNER_SERVICO, declaradas)


def capacidades_faltantes(executor: CapacidadesExecutor, requisitos: Iterable[str]) -> tuple[str, ...]:
    exigidas = _normalizar(requisitos, "requisitos")
    return tuple(sorted(exigidas - executor.capacidades))


def reservar_pedido_para_executor(
    pedido: PedidoDuravel,
    executor: CapacidadesExecutor,
    requisitos: Iterable[str],
    run_id: str,
    agora: datetime | None = None,
    duracao_segundos: float = DEFAULT_LEASE_SEGUNDOS,
) -> PedidoDuravel:
    """Mesma reserva do runner (lease/geração/run), com checagem prévia de
    capacidade. Levanta `CapacidadeInsuficiente` sem alterar nada e
    `DisputaPerdida` se o pedido já foi reservado por outro executor ou se
    uma retentativa agendada ainda não chegou na hora (o motivo vai na mensagem).

    A função é pura: dois executores que partem do MESMO snapshot pendente
    reservam os dois em memória. A exclusão real exige compare-and-set por
    geração/status na gravação (wiring Firestore, sub-entrega futura)."""
    if not isinstance(pedido, PedidoDuravel) or not isinstance(executor, CapacidadesExecutor):
        raise TypeError("pedido e executor devem ser PedidoDuravel e CapacidadesExecutor.")
    if (
        isinstance(duracao_segundos, bool)
        or not isinstance(duracao_segundos, (int, float))
        or not 0 < duracao_segundos <= _MAX_LEASE_SEGUNDOS  # nan/inf/int enorme falham aqui
    ):
        raise ValueError(f"duracao_segundos deve estar em (0, {_MAX_LEASE_SEGUNDOS}].")
    faltantes = capacidades_faltantes(executor, requisitos)
    if faltantes:
        raise CapacidadeInsuficiente(faltantes)
    if pedido.status not in (RequestStatus.PENDENTE, RequestStatus.RETENTATIVA_AGENDADA):
        raise DisputaPerdida(f"pedido em '{pedido.status.value}' não é reservável.")
    try:
        return assumir_pedido(
            pedido, executor.executor_id, run_id, agora=agora, duracao_segundos=duracao_segundos
        )
    except LeaseInvalida as exc:
        raise DisputaPerdida(str(exc)) from exc
