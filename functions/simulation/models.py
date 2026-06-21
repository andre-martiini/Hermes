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
    DONE = "done"
    REJECTED = "rejected"         # aprovacao negada
    FAILED = "failed"


class ApprovalStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SimStatus:
    PLANNING = "planning"
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"


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
class Task:
    """Uma unidade de trabalho a ser executada por um agente de um setor."""
    title: str
    sector: str
    description: str = ""
    tool: str | None = None       # ferramenta do registry que a tarefa pretende usar
    params: dict = field(default_factory=dict)
    status: str = TaskStatus.PENDING
    assignee_id: str | None = None
    depends_on: list[str] = field(default_factory=list)  # ids de outras tarefas
    result: str | None = None
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
class Simulation:
    """Estado de alto nivel de uma rodada de simulacao."""
    goal: str
    status: str = SimStatus.PLANNING
    created_at: float = field(default_factory=_now)
    id: str = field(default_factory=lambda: _new_id("sim"))

    def to_dict(self) -> dict:
        return asdict(self)
