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
    Branch,
    ExecutorType,
    Handoff,
    HandoffKind,
    HandoffStatus,
    SimEvent,
    SimMode,
    Simulation,
    SimStatus,
    Task,
    TaskKind,
    TaskStatus,
)
from .orchestrator import Planner, plan, plan_from_action
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


# Decider: dado um no' de decisao e seus ramos, retorna o id do ramo escolhido.
Decider = Callable[[Task, list[Branch]], str]


def first_branch_decider(task: Task, branches: list[Branch]) -> str:
    """Decider offline e determinista: escolhe o primeiro ramo. Seam para o Gemini."""
    return branches[0].id


class SimulationEngine:
    def __init__(
        self,
        store: SimulationStore | None = None,
        company: list[Agent] | None = None,
        executor: Executor | None = None,
        needs_confirmation: Callable[[str | None], bool] | None = None,
        decider: Decider | None = None,
    ) -> None:
        self.store = store or InMemoryStore()
        self.company = company or default_company()
        self.executor = executor or dry_run_executor
        self.needs_confirmation = needs_confirmation or _registry_needs_confirmation
        self.decider = decider or first_branch_decider

    # --- Setup ---

    def start(self, goal: str, planner: Planner | None = None,
              mode: str = SimMode.LIVE) -> Simulation:
        sim = Simulation(goal=goal, status=SimStatus.PLANNING, mode=mode)
        sectors = self._seed(sim, goal)
        tasks = plan(goal, sectors, planner)
        return self._finalize_start(sim, tasks)

    def start_from_action(self, action: dict, planner: Planner | None = None,
                          mode: str = SimMode.LIVE) -> Simulation:
        """Ativa os agentes sobre uma Tarefa REAL do Hermes (apenas leitura dela).

        `action` e' o dict da Tarefa (titulo, descricao, plano_de_acao). Nada e'
        escrito de volta na acao real; tudo vai para o namespace de simulacao.
        """
        title = action.get("titulo") or action.get("title") or "Acao"
        desc = action.get("descricao") or action.get("description") or ""
        goal = f"{title}. {desc}".strip()
        sim = Simulation(goal=goal, status=SimStatus.PLANNING, mode=mode,
                         source_action_id=action.get("id"))
        sectors = self._seed(sim, goal)
        tasks = plan_from_action(action, sectors, planner)
        return self._finalize_start(sim, tasks)

    def _seed(self, sim: Simulation, goal: str) -> list[str]:
        self.store.save_sim(sim)
        for agent in self.company:
            self.store.add_agent(agent)
        self._emit("sim_started", f"Objetivo definido: {goal}",
                   data={"mode": sim.mode, "source_action_id": sim.source_action_id})
        return sorted({a.sector for a in self.company})

    def _finalize_start(self, sim: Simulation, tasks: list[Task]) -> Simulation:
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

            # (a) Passo SO'-humano -> handoff (pausa e espera a pessoa fazer/decidir).
            if task.executor_type == ExecutorType.HUMAN:
                self._raise_handoff(task, agent)
                progressed = True
                continue

            # (b) No' de decisao executavel pelo agente -> escolhe um ramo e poda os outros.
            if task.kind == TaskKind.DECISION:
                branch_id = self.decider(task, task.branches)
                self._apply_decision(task, agent, branch_id, decided_by=agent.name)
                progressed = True
                continue

            # (c) Acao sensivel -> gera aprovacao e PARA.
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

            # (d) Acao normal -> executa em dry-run e conclui.
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

    # --- Handoff humano (passo so'-humano: pessoa executa/decide e devolve) ---

    def _raise_handoff(self, task: Task, agent: Agent) -> None:
        kind = HandoffKind.DECISION if task.kind == TaskKind.DECISION else HandoffKind.WORK
        options = [{"id": b.id, "label": b.label, "criteria": b.criteria}
                   for b in task.branches] if kind == HandoffKind.DECISION else []
        hand = Handoff(task_id=task.id, agent_id=agent.id, kind=kind,
                       instructions=task.description or task.title, options=options)
        self.store.add_handoff(hand)
        task.status = TaskStatus.AWAITING_HUMAN
        agent.status = AgentStatus.BLOCKED   # esperando insumo humano
        self.store.update_task(task)
        self.store.update_agent(agent)
        self._emit("handoff_requested",
                   f"{agent.name} escalou para um humano: '{task.title}'.",
                   agent_id=agent.id, task_id=task.id,
                   data={"handoff_id": hand.id, "kind": kind})

    def resolve_handoff(self, handoff_id: str, result: str | None = None,
                        chosen_branch_id: str | None = None,
                        decided_by: str = "humano") -> None:
        hand = self.store.get_handoff(handoff_id)
        if not hand or hand.status != HandoffStatus.PENDING:
            return
        task = self.store.get_task(hand.task_id)
        agent = self._agent(hand.agent_id)

        hand.status = HandoffStatus.DONE
        hand.decided_by = decided_by
        hand.result = result
        hand.chosen_branch_id = chosen_branch_id
        self.store.update_handoff(hand)

        if not task:
            return

        if hand.kind == HandoffKind.DECISION:
            branch_id = chosen_branch_id or (task.branches[0].id if task.branches else None)
            self._apply_decision(task, agent, branch_id, decided_by=decided_by)
        else:
            # Passo de trabalho: a pessoa fez e devolveu o resultado; o fluxo retoma.
            if agent:
                agent.status = AgentStatus.IDLE
                agent.current_task_id = None
                self.store.update_agent(agent)
            task.status = TaskStatus.DONE
            task.result = result or "Concluido por humano."
            self.store.update_task(task)
            self._emit("handoff_done",
                       f"Humano concluiu '{task.title}'.",
                       agent_id=hand.agent_id, task_id=task.id,
                       data={"result": task.result})

    def _apply_decision(self, task: Task, agent: Agent | None, branch_id: str | None,
                        decided_by: str) -> None:
        """Resolve um no' de decisao: ativa o ramo escolhido e poda os demais."""
        chosen = next((b for b in task.branches if b.id == branch_id), None)
        if chosen is None and task.branches:
            chosen = task.branches[0]

        task.kind = TaskKind.DECISION
        task.chosen_branch_id = chosen.id if chosen else None
        task.status = TaskStatus.DONE
        task.result = f"Decisao: {chosen.label}" if chosen else "Decisao sem ramos."
        self.store.update_task(task)

        if agent:
            agent.status = AgentStatus.IDLE
            agent.current_task_id = None
            self.store.update_agent(agent)

        # Poda: tarefas dos ramos NAO escolhidos viram SKIPPED.
        for branch in task.branches:
            if chosen and branch.id == chosen.id:
                continue
            for tid in branch.unlocks:
                pruned = self.store.get_task(tid)
                if pruned and pruned.status == TaskStatus.PENDING:
                    pruned.status = TaskStatus.SKIPPED
                    pruned.result = f"Ramo descartado ('{branch.label}')."
                    self.store.update_task(pruned)
                    self._emit("branch_pruned", f"Caminho descartado: {pruned.title}",
                               task_id=pruned.id)

        self._emit("decision_made",
                   f"Decisao '{task.title}': {chosen.label if chosen else 'n/a'} (por {decided_by}).",
                   agent_id=agent.id if agent else None, task_id=task.id,
                   data={"chosen_branch_id": task.chosen_branch_id, "decided_by": decided_by})

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
        # Uma dependencia esta' satisfeita se chegou a um estado terminal
        # (concluida, rejeitada, podada ou falha) -- assim ramos podados (SKIPPED)
        # nao travam os nos de juncao (ex: a consolidacao final).
        settled_ids = {t.id for t in self.store.list_tasks()
                       if t.status in TaskStatus.TERMINAL}
        ready = []
        for t in self.store.list_tasks():
            if t.status != TaskStatus.PENDING:
                continue
            if all(dep in settled_ids for dep in t.depends_on):
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
        active = (TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS)
        for t in self.store.list_tasks():
            if t.status in active:
                return False
        # Ainda ha' trabalho parado esperando um humano? Entao nao terminou.
        if self.store.list_pending_approvals() or self.store.list_pending_handoffs():
            return False
        return True

    def _emit(self, type_: str, message: str, agent_id: str | None = None,
              task_id: str | None = None, data: dict | None = None) -> None:
        self.store.add_event(SimEvent(type=type_, message=message,
                                      agent_id=agent_id, task_id=task_id,
                                      data=data or {}))
