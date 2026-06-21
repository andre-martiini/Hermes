"""Estruturas de dados da simulacao de empresa.

Tudo aqui e' serializavel para dict (`to_dict`) para gravacao em Firestore no
namespace isolado e para consumo pela camada grafica.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _now() -> float:
    return time.time()


# --- Enums (como constantes de string para casar com o estilo do projeto) ---

class AgentStatus:
    IDLE = "idle"                 # parado, disponivel
    WORKING = "working"           # executando uma tarefa
    WAITING_APPROVAL = "waiting_approval"  # parou aguardando o presidente
    BLOCKED = "blocked"           # esperando dependencia/insumo


class TaskStatus:
    PENDING = "pending"           # criada, sem dono
    ASSIGNED = "assigned"         # atribuida a um agente
    IN_PROGRESS = "in_progress"   # sendo executada
    AWAITING_APPROVAL = "awaiting_approval"  # acao sensivel parada para aprovacao
    AWAITING_HUMAN = "awaiting_human"  # passo so'-humano: pessoa precisa fazer/decidir
    DONE = "done"
    REJECTED = "rejected"         # aprovacao negada
    SKIPPED = "skipped"           # ramo de decisao nao escolhido (podado)
    FAILED = "failed"

    # Estados terminais: satisfazem dependencias e nao impedem o fim da simulacao.
    TERMINAL = (DONE, REJECTED, SKIPPED, FAILED)


class TaskKind:
    WORK = "work"                 # tarefa de execucao comum
    DECISION = "decision"         # no' de decisao: escolhe um ramo e poda os outros


class ExecutorType:
    AGENT = "agent"               # um agente executa
    HUMAN = "human"               # so' um humano pode executar/decidir (handoff)
    EITHER = "either"             # tanto faz; o engine prefere o agente


class ApprovalStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class HandoffKind:
    WORK = "work"                 # humano precisa EXECUTAR e devolver um resultado
    DECISION = "decision"         # humano precisa ESCOLHER um ramo


class HandoffStatus:
    PENDING = "pending"
    DONE = "done"


class SimStatus:
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"


class SimMode:
    LIVE = "live"                 # palco: UI assina os eventos e anima em tempo real
    BACKGROUND = "background"     # bastidores: roda sozinho e so' persiste o resultado


# --- Modelos ---

@dataclass
class Agent:
    """Um funcionario da empresa simulada."""
    name: str
    role: str                     # titulo do cargo (ex: "Analista Financeiro")
    sector: str                   # setor/area (ver roles.Sector)
    persona: str = ""             # personalidade que tempera as decisoes do agente
    allowed_tools: list[str] = field(default_factory=list)  # subset do registry real
    status: str = AgentStatus.IDLE
    current_task_id: str | None = None
    id: str = field(default_factory=lambda: _new_id("agent"))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Branch:
    """Um caminho possivel a partir de um no' de decisao."""
    label: str
    unlocks: list[str] = field(default_factory=list)  # ids de tarefas que este ramo ativa
    criteria: str = ""            # dica para o agente/humano sobre quando seguir este ramo
    id: str = field(default_factory=lambda: _new_id("branch"))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Task:
    """Uma unidade de trabalho (ou um no' de decisao) de um setor."""
    title: str
    sector: str
    description: str = ""
    kind: str = TaskKind.WORK
    executor_type: str = ExecutorType.AGENT   # agent | human | either
    tool: str | None = None       # ferramenta do registry que a tarefa pretende usar
    params: dict = field(default_factory=dict)
    branches: list[Branch] = field(default_factory=list)  # so' para kind == DECISION
    status: str = TaskStatus.PENDING
    assignee_id: str | None = None
    depends_on: list[str] = field(default_factory=list)  # ids de outras tarefas
    result: str | None = None
    chosen_branch_id: str | None = None  # ramo escolhido (apos resolver a decisao)
    created_at: float = field(default_factory=_now)
    id: str = field(default_factory=lambda: _new_id("task"))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SimEvent:
    """Evento no stream da simulacao. A camada grafica renderiza estes eventos."""
    type: str                     # ex: "agent_started", "task_done", "approval_requested"
    message: str
    agent_id: str | None = None
    task_id: str | None = None
    data: dict = field(default_factory=dict)
    ts: float = field(default_factory=_now)
    id: str = field(default_factory=lambda: _new_id("evt"))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Approval:
    """Pedido de autorizacao para uma acao sensivel. O 'presidente' (humano) decide."""
    task_id: str
    agent_id: str
    tool: str
    params: dict = field(default_factory=dict)
    status: str = ApprovalStatus.PENDING
    decided_by: str | None = None
    reason: str | None = None
    created_at: float = field(default_factory=_now)
    id: str = field(default_factory=lambda: _new_id("appr"))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Handoff:
    """Passo que SO' um humano pode tocar: executar e devolver, ou escolher um ramo.

    Diferente de Approval: na aprovacao o agente ja' faz e o humano so' valida (sim/nao);
    aqui o agente NAO consegue produzir o resultado -- a pessoa faz/decide e devolve.
    """
    task_id: str
    agent_id: str | None        # agente que escalou (pode ser None)
    kind: str = HandoffKind.WORK
    instructions: str = ""      # o que o agente precisa que a pessoa faca/decida
    options: list[dict] = field(default_factory=list)  # ramos disponiveis (kind=decision)
    status: str = HandoffStatus.PENDING
    result: str | None = None           # resultado devolvido pela pessoa (kind=work)
    chosen_branch_id: str | None = None  # ramo escolhido pela pessoa (kind=decision)
    decided_by: str | None = None
    created_at: float = field(default_factory=_now)
    id: str = field(default_factory=lambda: _new_id("hand"))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Simulation:
    """Estado de alto nivel de uma rodada de simulacao."""
    goal: str
    status: str = SimStatus.PLANNING
    mode: str = SimMode.LIVE      # live (palco) | background (bastidores)
    source_action_id: str | None = None  # Tarefa real do Hermes que originou a simulacao
    created_at: float = field(default_factory=_now)
    id: str = field(default_factory=lambda: _new_id("sim"))

    def to_dict(self) -> dict:
        return asdict(self)
