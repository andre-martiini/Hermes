"""Engine da simulacao: o loop de execucao da empresa de agentes.

Responsabilidades:
- Iniciar uma simulacao a partir de um objetivo (usa o orchestrator para planejar).
- A cada tick: atribuir tarefas prontas a agentes ociosos do setor certo e executa-las.
- Gating de aprovacao: acoes sensiveis (needs_confirmation no registry real) PARAM e
  geram um Approval que o presidente (humano) precisa aprovar/rejeitar.
- Emitir SimEvents que a camada grafica consome.

Execucao e' DRY-RUN por padrao: nenhuma ferramenta real e' chamada e nada sai do
namespace de simulacao. O resultado e' simulado. Trocar para execucao real e' um
seam futuro (executor plugavel).
"""

from __future__ import annotations

from typing import Callable

from .models import (
    Agent,
    AgentStatus,
    Approval,
    ApprovalStatus,
    SimEvent,
    Simulation,
    SimStatus,
    Task,
    TaskStatus,
)
from .orchestrator import Planner, plan
from .roles import default_company
from .store import InMemoryStore, SimulationStore


def _registry_needs_confirmation(tool: str | None) -> bool:
    """Usa a regra REAL do Hermes para saber se a acao precisa de aprovacao."""
    if not tool:
        return False
    try:
        from tools.registry import needs_confirmation
        return needs_confirmation(tool)
    except Exception:
        # Fallback conservador: trata mutacoes conhecidas como sensiveis.
        sensitive_prefixes = ("registrar_", "criar_", "mutar_", "editar_", "schedule_", "salvar_")
        return tool.startswith(sensitive_prefixes)


# Executor: (Agent, Task) -> texto de resultado. Default = dry-run simulado.
Executor = Callable[[Agent, Task], str]


def dry_run_executor(agent: Agent, task: Task) -> str:
    tool = task.tool or "(sem ferramenta)"
    return f"[DRY-RUN] {agent.name} executou '{task.title}' via {tool}."


class SimulationEngine:
    def __init__(
        self,
        store: SimulationStore | None = None,
        company: list[Agent] | None = None,
        executor: Executor | None = None,
        needs_confirmation: Callable[[str | None], bool] | None = None,
    ) -> None:
        self.store = store or InMemoryStore()
        self.company = company or default_company()
        self.executor = executor or dry_run_executor
        self.needs_confirmation = needs_confirmation or _registry_needs_confirmation

    # --- Setup ---

    def start(self, goal: str, planner: Planner | None = None) -> Simulation:
        sim = Simulation(goal=goal, status=SimStatus.PLANNING)
        self.store.save_sim(sim)

        for agent in self.company:
            self.store.add_agent(agent)
        self._emit("sim_started", f"Objetivo definido: {goal}")

        sectors = sorted({a.sector for a in self.company})
        tasks = plan(goal, sectors, planner)
        for task in tasks:
            self.store.add_task(task)
        self._emit("plan_ready", f"{len(tasks)} tarefas planejadas pela Diretoria.",
                   data={"task_count": len(tasks)})

        sim.status = SimStatus.RUNNING
        self.store.save_sim(sim)
        return sim

    # --- Loop ---

    def tick(self) -> bool:
        """Executa um passo. Retorna True se houve progresso."""
        progressed = False

        # 1) Atribuir tarefas prontas a agentes ociosos.
        for task in self._ready_tasks():
            agent = self._free_agent_for(task.sector)
            if not agent:
                continue
            task.status = TaskStatus.ASSIGNED
            task.assignee_id = agent.id
            agent.status = AgentStatus.WORKING
            agent.current_task_id = task.id
            self.store.update_task(task)
            self.store.update_agent(agent)
            self._emit("agent_assigned", f"{agent.name} pegou: {task.title}",
                       agent_id=agent.id, task_id=task.id)
            progressed = True

        # 2) Processar tarefas atribuidas/em progresso.
        for task in self.store.list_tasks():
            if task.status != TaskStatus.ASSIGNED:
                continue
            agent = self._agent(task.assignee_id)
            if not agent:
                continue

            # Acao sensivel -> gera aprovacao e PARA.
            if self.needs_confirmation(task.tool):
                appr = Approval(task_id=task.id, agent_id=agent.id,
                                tool=task.tool or "", params=task.params)
                self.store.add_approval(appr)
                task.status = TaskStatus.AWAITING_APPROVAL
                agent.status = AgentStatus.WAITING_APPROVAL
                self.store.update_task(task)
                self.store.update_agent(agent)
                self._emit("approval_requested",
                           f"{agent.name} aguarda aprovacao do presidente para '{task.title}'.",
                           agent_id=agent.id, task_id=task.id,
                           data={"approval_id": appr.id, "tool": task.tool})
                progressed = True
                continue

            # Acao normal -> executa em dry-run e conclui.
            result = self.executor(agent, task)
            self._complete_task(task, agent, result)
            progressed = True

        # 3) Fecha a simulacao se nada esta' pendente nem bloqueando.
        if self._all_settled():
            sim = self.store.get_sim()
            if sim and sim.status == SimStatus.RUNNING:
                sim.status = SimStatus.DONE
                self.store.save_sim(sim)
                self._emit("sim_done", "Empresa concluiu o ciclo de trabalho.")

        return progressed

    def run_until_idle(self, max_ticks: int = 100) -> int:
        """Roda ticks ate' nao haver mais progresso (ex: aguardando aprovacoes)."""
        ticks = 0
        while ticks < max_ticks:
            if not self.tick():
                break
            ticks += 1
        return ticks

    # --- Aprovacao (presidente humano) ---

    def resolve_approval(self, approval_id: str, approved: bool,
                         decided_by: str = "presidente", reason: str | None = None) -> None:
        appr = self.store.get_approval(approval_id)
        if not appr or appr.status != ApprovalStatus.PENDING:
            return
        task = self.store.get_task(appr.task_id)
        agent = self._agent(appr.agent_id)

        appr.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        appr.decided_by = decided_by
        appr.reason = reason
        self.store.update_approval(appr)

        if not task or not agent:
            return

        if approved:
            result = self.executor(agent, task)
            self._complete_task(task, agent, result)
            self._emit("approval_granted",
                       f"Presidente aprovou '{task.title}'. {agent.name} executou.",
                       agent_id=agent.id, task_id=task.id)
        else:
            task.status = TaskStatus.REJECTED
            task.result = f"Rejeitada pelo presidente: {reason or 'sem motivo'}"
            agent.status = AgentStatus.IDLE
            agent.current_task_id = None
            self.store.update_task(task)
            self.store.update_agent(agent)
            self._emit("approval_denied",
                       f"Presidente rejeitou '{task.title}'.",
                       agent_id=agent.id, task_id=task.id)

    # --- Helpers ---

    def _complete_task(self, task: Task, agent: Agent, result: str) -> None:
        task.status = TaskStatus.DONE
        task.result = result
        agent.status = AgentStatus.IDLE
        agent.current_task_id = None
        self.store.update_task(task)
        self.store.update_agent(agent)
        self._emit("task_done", f"{agent.name} concluiu: {task.title}",
                   agent_id=agent.id, task_id=task.id, data={"result": result})

    def _ready_tasks(self) -> list[Task]:
        done_ids = {t.id for t in self.store.list_tasks() if t.status == TaskStatus.DONE}
        ready = []
        for t in self.store.list_tasks():
            if t.status != TaskStatus.PENDING:
                continue
            if all(dep in done_ids for dep in t.depends_on):
                ready.append(t)
        return ready

    def _free_agent_for(self, sector: str) -> Agent | None:
        for a in self.store.list_agents():
            if a.sector == sector and a.status == AgentStatus.IDLE:
                return a
        return None

    def _agent(self, agent_id: str | None) -> Agent | None:
        if not agent_id:
            return None
        for a in self.store.list_agents():
            if a.id == agent_id:
                return a
        return None

    def _all_settled(self) -> bool:
        for t in self.store.list_tasks():
            if t.status in (TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS):
                return False
        return True

    def _emit(self, type_: str, message: str, agent_id: str | None = None,
              task_id: str | None = None, data: dict | None = None) -> None:
        self.store.add_event(SimEvent(type=type_, message=message,
                                      agent_id=agent_id, task_id=task_id,
                                      data=data or {}))
