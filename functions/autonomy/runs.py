"""Ciclo verificado de agent_run (P04 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, passo 2 do pacote: "Servidor cria
agent_run ao reservar/iniciar; conclusão e timeout são transições
verificadas, não simples add de resumo").

Achado A02 do plano: "agent_runs.py: registrar grava um resumo final, sem
ciclo obrigatório de início/heartbeat -- uma execução que nunca termina pode
desaparecer das métricas." O `agent_runs.py` legado (`registrar`) continua
existindo e não é alterado por este módulo -- ele grava um resumo textual
livre (rotina/resumo/contadores) útil para métricas históricas, mas não
representa um CICLO verificado por identidade de lease de UMA tentativa de
execução de UM pedido.

Este módulo modela esse ciclo como lógica pura, mesmo padrão incremental já
usado em `autonomy.requests` (passo 1), `autonomy.ledger` (passo 3) e
`autonomy.execution` (passo 4, que já costurou os dois anteriores): sem
nenhum I/O aqui. Quem persiste o `AgentRun` (Firestore) e quem chama
`criar_run` no mesmo instante em que `autonomy.execution.assumir_pedido`
emite uma lease nova fica para a sub-entrega de wiring (passo 5/6 do
pacote) -- ver `proximo_pacote` do bloco desta sub-entrega em
docs/autonomia/execucao.md.

Um `AgentRun` representa UMA tentativa de execução (uma lease/geração) de um
pedido durável -- distinto do próprio pedido
(`autonomy.execution.PedidoDuravel`), que pode atravessar VÁRIAS tentativas:
cada `RETENTATIVA_AGENDADA` seguida de um novo `assumir_pedido` produz uma
nova geração e, com o wiring futuro, um novo `AgentRun`. Por isso o
`run_id` é próprio (não reusa `request_id`) e o fencing de ações sobre um
`AgentRun` compara identidade (token + geração) contra os valores capturados
na criação do próprio run, não contra uma `Lease` viva -- este módulo
deliberadamente não importa `autonomy.requests.Lease` para não acoplar o
ciclo do run à representação de reserva do pedido; só reaproveita o mesmo
raciocínio de fencing (comparação em tempo constante do token, geração
monotônica) já estabelecido lá.
"""

from __future__ import annotations

import dataclasses
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AgentRunStatus(str, Enum):
    """Ciclo de vida de UMA tentativa de execução de um pedido."""

    INICIADO = "iniciado"
    EM_ANDAMENTO = "em_andamento"
    CONCLUIDO = "concluido"
    FALHA = "falha"
    TIMEOUT = "timeout"


#: Nenhuma transição de saída -- mesmo espírito de
#: `autonomy.requests.ESTADOS_TERMINAIS`.
ESTADOS_TERMINAIS: frozenset[AgentRunStatus] = frozenset({
    AgentRunStatus.CONCLUIDO,
    AgentRunStatus.FALHA,
    AgentRunStatus.TIMEOUT,
})


_TRANSICOES_PERMITIDAS: dict[AgentRunStatus, frozenset[AgentRunStatus]] = {
    AgentRunStatus.INICIADO: frozenset({
        AgentRunStatus.EM_ANDAMENTO,
        # Uma tentativa pode falhar/concluir/estourar o tempo antes de
        # qualquer checkpoint -- não força passar por EM_ANDAMENTO.
        AgentRunStatus.CONCLUIDO,
        AgentRunStatus.FALHA,
        AgentRunStatus.TIMEOUT,
    }),
    AgentRunStatus.EM_ANDAMENTO: frozenset({
        AgentRunStatus.CONCLUIDO,
        AgentRunStatus.FALHA,
        AgentRunStatus.TIMEOUT,
    }),
    AgentRunStatus.CONCLUIDO: frozenset(),
    AgentRunStatus.FALHA: frozenset(),
    AgentRunStatus.TIMEOUT: frozenset(),
}


def transicoes_permitidas(status_atual: AgentRunStatus) -> frozenset[AgentRunStatus]:
    """Destinos permitidos a partir de `status_atual`. Falha fechada (conjunto
    vazio) para um valor não mapeado."""
    return _TRANSICOES_PERMITIDAS.get(status_atual, frozenset())


def _validar_transicao(status_atual: AgentRunStatus, status_novo: AgentRunStatus) -> tuple[bool, str]:
    if status_atual == status_novo:
        return False, f"run já está em '{status_atual.value}'"
    if status_atual in ESTADOS_TERMINAIS:
        return False, f"'{status_atual.value}' é terminal, não transiciona para nada"
    permitidas = transicoes_permitidas(status_atual)
    if status_novo not in permitidas:
        return False, (
            f"transição '{status_atual.value}' -> '{status_novo.value}' não é permitida "
            f"(permitidas a partir de '{status_atual.value}': "
            f"{sorted(s.value for s in permitidas) or 'nenhuma'})"
        )
    return True, ""


def _exigir_tz_aware(dt: datetime, nome_param: str) -> None:
    """Mesma checagem de `autonomy.requests._exigir_tz_aware` -- duplicada
    aqui (não importada) para manter este módulo sem dependência de
    `autonomy.requests`, ver docstring do módulo."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(
            f"{nome_param} deve ser timezone-aware (ex.: datetime.now(timezone.utc)); "
            f"recebido: {dt!r}"
        )


class RunFinalizado(Exception):
    """Levantada ao tentar transicionar um `AgentRun` já terminal para
    qualquer outro estado (inclusive um terminal diferente) -- um run
    concluído/com falha/com timeout nunca regride nem troca de desfecho."""

    def __init__(self, motivo: str) -> None:
        self.motivo = motivo
        super().__init__(motivo)


class RunLeaseInvalida(Exception):
    """Fencing falhou: token/geração apresentados não conferem com os que
    identificam este `AgentRun`. Mesmo espírito de
    `autonomy.execution.LeaseInvalida`, para o ciclo do run."""

    def __init__(self, motivo: str) -> None:
        self.motivo = motivo
        super().__init__(f"lease inválida para agent_run: {motivo}")


@dataclass(frozen=True)
class AgentRun:
    """Um registro verificado de UMA tentativa de execução. Imutável --
    toda função abaixo devolve uma instância NOVA, nunca muta esta."""

    run_id: str
    request_id: str
    executor_id: str
    lease_token: str
    generation: int
    status: AgentRunStatus
    iniciado_em: datetime
    finalizado_em: datetime | None = None
    resultado: Any = None

    def __post_init__(self) -> None:
        run_id_limpo = str(self.run_id or "").strip()
        if not run_id_limpo:
            raise ValueError("run_id é obrigatório.")
        request_id_limpo = str(self.request_id or "").strip()
        if not request_id_limpo:
            raise ValueError("request_id é obrigatório.")
        executor_id_limpo = str(self.executor_id or "").strip()
        if not executor_id_limpo:
            raise ValueError("executor_id é obrigatório.")
        lease_token_limpo = str(self.lease_token or "").strip()
        if not lease_token_limpo:
            raise ValueError("lease_token é obrigatório.")
        if self.generation < 1:
            raise ValueError("generation deve ser >= 1 (mesma convenção de autonomy.requests.Lease).")
        _exigir_tz_aware(self.iniciado_em, "iniciado_em")
        if self.finalizado_em is not None:
            _exigir_tz_aware(self.finalizado_em, "finalizado_em")
        object.__setattr__(self, "run_id", run_id_limpo)
        object.__setattr__(self, "request_id", request_id_limpo)
        object.__setattr__(self, "executor_id", executor_id_limpo)
        object.__setattr__(self, "lease_token", lease_token_limpo)


def _fencing_run(run: AgentRun, lease_token: str, generation: int) -> None:
    """Confere só IDENTIDADE (token + geração apresentados contra os que
    criaram este `AgentRun`) -- SEM checar expiração de lease nenhuma: um
    `AgentRun` não guarda `expires_at` próprio (quem decide timeout é
    `expirar_por_timeout`, a partir da lease REAL do pedido, não daqui).
    Comparação de token em tempo constante, mesma técnica de
    `autonomy.requests.lease_pertence_ao_apresentante`."""
    try:
        generation_normalizada = int(generation)
    except (TypeError, ValueError, OverflowError):
        raise RunLeaseInvalida("geração apresentada não é um inteiro válido")
    if run.generation != generation_normalizada:
        raise RunLeaseInvalida("geração não confere (reserva perdida para outro executor)")
    try:
        token_confere = secrets.compare_digest(run.lease_token, str(lease_token or ""))
    except TypeError:
        token_confere = False
    if not token_confere:
        raise RunLeaseInvalida("token de reserva não confere")


def criar_run(
    run_id: str,
    request_id: str,
    executor_id: str,
    lease_token: str,
    generation: int,
    agora: datetime | None = None,
) -> AgentRun:
    """Seção 1.3, A02 / seção 8, P04 passo 2: "servidor cria agent_run ao
    reservar/iniciar." Chamar isto no MESMO instante em que
    `autonomy.execution.assumir_pedido` emite uma lease nova, passando o
    `lease_token`/`generation` recém-emitidos -- este módulo não gera lease
    nenhuma, só registra o ciclo verificado de UMA tentativa a partir de uma
    já existente.

    `run_id` deve ser um identificador NOVO por tentativa (não reusar
    `request_id`): múltiplas tentativas do mesmo pedido produzem múltiplos
    `AgentRun`, todos consultáveis por `request_id`. Este módulo não decide
    como gerar esse identificador (isso é wiring -- Firestore auto-ID ou
    `secrets.token_urlsafe`, à escolha de quem persistir)."""
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    agora_utc = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return AgentRun(
        run_id=run_id,
        request_id=request_id,
        executor_id=executor_id,
        lease_token=lease_token,
        generation=generation,
        status=AgentRunStatus.INICIADO,
        iniciado_em=agora_utc,
    )


def marcar_em_andamento(
    run: AgentRun,
    lease_token: str,
    generation: int,
) -> AgentRun:
    """Primeiro checkpoint de uma tentativa: `INICIADO -> EM_ANDAMENTO`.
    Chamadas seguintes enquanto já `EM_ANDAMENTO` são um no-op idempotente
    (heartbeat/checkpoint repetido), mesmo padrão de
    `autonomy.execution.registrar_progresso` para o pedido."""
    _fencing_run(run, lease_token, generation)
    if run.status == AgentRunStatus.EM_ANDAMENTO:
        return run
    ok, motivo = _validar_transicao(run.status, AgentRunStatus.EM_ANDAMENTO)
    if not ok:
        if run.status in ESTADOS_TERMINAIS:
            raise RunFinalizado(motivo)
        raise ValueError(motivo)
    return dataclasses.replace(run, status=AgentRunStatus.EM_ANDAMENTO)


def concluir_run(
    run: AgentRun,
    lease_token: str,
    generation: int,
    novo_status: AgentRunStatus,
    resultado: Any = None,
    agora: datetime | None = None,
) -> AgentRun:
    """Seção 1.3, A02: conclusão é uma transição VERIFICADA, não um
    resumo adicionado livremente. Só aceita `CONCLUIDO` ou `FALHA` como
    `novo_status` -- `TIMEOUT` é decidido exclusivamente por
    `expirar_por_timeout`, uma ação de sistema, nunca pelo próprio executor
    se autodeclarando "deu timeout".

    Reentrega do MESMO resultado para um run já terminal é idempotente e
    ainda exige identidade (token/geração), mas SEM exigir que uma lease
    ainda esteja "viva" -- mesma razão de
    `autonomy.execution.registrar_resultado_observado`: uma resposta
    perdida por timeout de rede pode ser reapresentada bem depois do
    vencimento natural da lease original. Resultado DIFERENTE para o mesmo
    run terminal, ou tentar concluir um run já terminal com um status
    diferente, levanta erro -- nunca sobrescreve."""
    if novo_status not in (AgentRunStatus.CONCLUIDO, AgentRunStatus.FALHA):
        raise ValueError(
            "concluir_run só aceita 'concluido' ou 'falha' como novo_status -- "
            "timeout é decidido por expirar_por_timeout, não por esta função."
        )
    if run.status in ESTADOS_TERMINAIS:
        _fencing_run(run, lease_token, generation)
        if run.status == novo_status and run.resultado == resultado:
            return run
        raise RunFinalizado(
            f"run '{run.run_id}' já está em estado terminal '{run.status.value}' -- "
            "não pode transicionar de novo (nem para o mesmo status com "
            "resultado diferente, nem para outro status)."
        )
    _fencing_run(run, lease_token, generation)
    ok, motivo = _validar_transicao(run.status, novo_status)
    if not ok:
        raise ValueError(motivo)
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    agora_utc = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return dataclasses.replace(
        run, status=novo_status, resultado=resultado, finalizado_em=agora_utc
    )


def expirar_por_timeout(
    run: AgentRun,
    lease_expirada: bool,
    agora: datetime | None = None,
) -> AgentRun:
    """Seção 1.3, A02: "timeout são transições verificadas, não simples add
    de resumo." Diferente de `concluir_run`, não exige token/geração
    apresentados -- é uma ação de SISTEMA (o sweep de leases vencidas do
    passo 7 do pacote, ainda não implementado nesta sub-entrega), não uma
    resposta do próprio executor que perdeu a reserva.

    Por isso exige explicitamente `lease_expirada=True`: só o `status` do
    run estar ativo não basta para provar que o timeout de fato ocorreu --
    quem chama precisa ter checado a lease REAL do pedido
    (`autonomy.requests.lease_expirada` sobre a `Lease` atual) e passar o
    resultado dessa checagem aqui. Isto impede produzir um `TIMEOUT`
    especulativo sem checar o relógio de verdade -- a mesma classe de
    problema que A02 aponta no `agent_runs.py` legado, só que na direção
    oposta (declarar timeout cedo demais em vez de nunca declarar)."""
    if run.status == AgentRunStatus.TIMEOUT:
        return run
    if run.status in ESTADOS_TERMINAIS:
        raise RunFinalizado(
            f"run '{run.run_id}' já está em estado terminal '{run.status.value}' -- "
            "não pode ser marcado como timeout."
        )
    if not lease_expirada:
        raise ValueError(
            f"run '{run.run_id}' não pode expirar por timeout -- a lease do pedido "
            "ainda não expirou (confira autonomy.requests.lease_expirada antes de chamar)."
        )
    if agora is not None:
        _exigir_tz_aware(agora, "agora")
    agora_utc = (agora or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return dataclasses.replace(run, status=AgentRunStatus.TIMEOUT, finalizado_em=agora_utc)


def run_esta_ativo(run: AgentRun) -> bool:
    """`True` quando `run.status` ainda não chegou a um desfecho terminal."""
    return run.status not in ESTADOS_TERMINAIS
