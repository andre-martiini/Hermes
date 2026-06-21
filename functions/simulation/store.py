"""Persistencia da simulacao.

Duas implementacoes:
- InMemoryStore: usada em testes e prototipagem; nao toca em rede.
- FirestoreSimulationStore: grava SOMENTE sob `simulation/{sim_id}/...`. O prefixo
  e' travado no construtor para garantir o isolamento exigido (nada de producao).

Ambas expoem a mesma interface (SimulationStore), entao o engine nao sabe qual
esta' usando.
"""

from __future__ import annotations

from typing import Protocol

from .models import Agent, Approval, Handoff, SimEvent, Simulation, Task


class SimulationStore(Protocol):
    def save_sim(self, sim: Simulation) -> None: ...
    def get_sim(self) -> Simulation | None: ...

    def add_agent(self, agent: Agent) -> None: ...
    def update_agent(self, agent: Agent) -> None: ...
    def list_agents(self) -> list[Agent]: ...

    def add_task(self, task: Task) -> None: ...
    def update_task(self, task: Task) -> None: ...
    def get_task(self, task_id: str) -> Task | None: ...
    def list_tasks(self) -> list[Task]: ...

    def add_event(self, event: SimEvent) -> None: ...
    def list_events(self, since_ts: float = 0.0) -> list[SimEvent]: ...

    def add_approval(self, approval: Approval) -> None: ...
    def update_approval(self, approval: Approval) -> None: ...
    def get_approval(self, approval_id: str) -> Approval | None: ...
    def list_pending_approvals(self) -> list[Approval]: ...

    def add_handoff(self, handoff: Handoff) -> None: ...
    def update_handoff(self, handoff: Handoff) -> None: ...
    def get_handoff(self, handoff_id: str) -> Handoff | None: ...
    def list_pending_handoffs(self) -> list[Handoff]: ...


class InMemoryStore:
    """Implementacao em memoria. Util para testes e para a UI consumir via export."""

    def __init__(self) -> None:
        self._sim: Simulation | None = None
        self._agents: dict[str, Agent] = {}
        self._tasks: dict[str, Task] = {}
        self._events: list[SimEvent] = []
        self._approvals: dict[str, Approval] = {}
        self._handoffs: dict[str, Handoff] = {}

    # Simulation
    def save_sim(self, sim: Simulation) -> None:
        self._sim = sim

    def get_sim(self) -> Simulation | None:
        return self._sim

    # Agents
    def add_agent(self, agent: Agent) -> None:
        self._agents[agent.id] = agent

    def update_agent(self, agent: Agent) -> None:
        self._agents[agent.id] = agent

    def list_agents(self) -> list[Agent]:
        return list(self._agents.values())

    # Tasks
    def add_task(self, task: Task) -> None:
        self._tasks[task.id] = task

    def update_task(self, task: Task) -> None:
        self._tasks[task.id] = task

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    # Events
    def add_event(self, event: SimEvent) -> None:
        self._events.append(event)

    def list_events(self, since_ts: float = 0.0) -> list[SimEvent]:
        return [e for e in self._events if e.ts >= since_ts]

    # Approvals
    def add_approval(self, approval: Approval) -> None:
        self._approvals[approval.id] = approval

    def update_approval(self, approval: Approval) -> None:
        self._approvals[approval.id] = approval

    def get_approval(self, approval_id: str) -> Approval | None:
        return self._approvals.get(approval_id)

    def list_pending_approvals(self) -> list[Approval]:
        from .models import ApprovalStatus
        return [a for a in self._approvals.values() if a.status == ApprovalStatus.PENDING]

    # Handoffs
    def add_handoff(self, handoff: Handoff) -> None:
        self._handoffs[handoff.id] = handoff

    def update_handoff(self, handoff: Handoff) -> None:
        self._handoffs[handoff.id] = handoff

    def get_handoff(self, handoff_id: str) -> Handoff | None:
        return self._handoffs.get(handoff_id)

    def list_pending_handoffs(self) -> list[Handoff]:
        from .models import HandoffStatus
        return [h for h in self._handoffs.values() if h.status == HandoffStatus.PENDING]


# Raiz fixa do namespace isolado. Nenhuma escrita acontece fora daqui.
SIMULATION_ROOT = "simulation"


class FirestoreSimulationStore:
    """Grava sob `simulation/{sim_id}/...` apenas. Lazy-import de firebase_admin.

    Estrutura:
        simulation/{sim_id}                 -> doc da simulacao
        simulation/{sim_id}/agents/{id}
        simulation/{sim_id}/tasks/{id}
        simulation/{sim_id}/events/{id}
        simulation/{sim_id}/approvals/{id}
    """

    def __init__(self, sim_id: str) -> None:
        if not sim_id:
            raise ValueError("sim_id obrigatorio para isolar o namespace")
        self.sim_id = sim_id
        self._db = None

    def _base(self):
        if self._db is None:
            from firebase_admin import firestore
            self._db = firestore.client()
        return self._db.collection(SIMULATION_ROOT).document(self.sim_id)

    def save_sim(self, sim: Simulation) -> None:
        self._base().set(sim.to_dict())

    def get_sim(self) -> Simulation | None:
        snap = self._base().get()
        if not snap.exists:
            return None
        return Simulation(**snap.to_dict())

    def _coll(self, name: str):
        return self._base().collection(name)

    def add_agent(self, agent: Agent) -> None:
        self._coll("agents").document(agent.id).set(agent.to_dict())

    update_agent = add_agent

    def list_agents(self) -> list[Agent]:
        return [Agent(**d.to_dict()) for d in self._coll("agents").stream()]

    def add_task(self, task: Task) -> None:
        self._coll("tasks").document(task.id).set(task.to_dict())

    update_task = add_task

    @staticmethod
    def _task_from_dict(data: dict) -> Task:
        from .models import Branch
        data = dict(data)
        data["branches"] = [Branch(**b) if isinstance(b, dict) else b
                            for b in data.get("branches", [])]
        return Task(**data)

    def get_task(self, task_id: str) -> Task | None:
        snap = self._coll("tasks").document(task_id).get()
        return self._task_from_dict(snap.to_dict()) if snap.exists else None

    def list_tasks(self) -> list[Task]:
        return [self._task_from_dict(d.to_dict()) for d in self._coll("tasks").stream()]

    def add_event(self, event: SimEvent) -> None:
        self._coll("events").document(event.id).set(event.to_dict())

    def list_events(self, since_ts: float = 0.0) -> list[SimEvent]:
        q = self._coll("events").where("ts", ">=", since_ts)
        return [SimEvent(**d.to_dict()) for d in q.stream()]

    def add_approval(self, approval: Approval) -> None:
        self._coll("approvals").document(approval.id).set(approval.to_dict())

    update_approval = add_approval

    def get_approval(self, approval_id: str) -> Approval | None:
        snap = self._coll("approvals").document(approval_id).get()
        return Approval(**snap.to_dict()) if snap.exists else None

    def list_pending_approvals(self) -> list[Approval]:
        from .models import ApprovalStatus
        q = self._coll("approvals").where("status", "==", ApprovalStatus.PENDING)
        return [Approval(**d.to_dict()) for d in q.stream()]

    def add_handoff(self, handoff: Handoff) -> None:
        self._coll("handoffs").document(handoff.id).set(handoff.to_dict())

    update_handoff = add_handoff

    def get_handoff(self, handoff_id: str) -> Handoff | None:
        snap = self._coll("handoffs").document(handoff_id).get()
        return Handoff(**snap.to_dict()) if snap.exists else None

    def list_pending_handoffs(self) -> list[Handoff]:
        from .models import HandoffStatus
        q = self._coll("handoffs").where("status", "==", HandoffStatus.PENDING)
        return [Handoff(**d.to_dict()) for d in q.stream()]
