"""Demo de linha de comando da empresa de agentes.

Roda uma simulacao offline (dry-run, namespace em memoria) e imprime o stream de
eventos como um "diario do escritorio". Serve para ver o comportamento logico
antes da camada grafica existir.

Uso:
    python -m simulation.demo "Reduzir custos e renegociar compras com fornecedores"
"""

import sys

from .engine import SimulationEngine
from .store import InMemoryStore
from .models import AgentStatus


def _print_events(store: InMemoryStore, since: int) -> int:
    events = store.list_events()
    for e in events[since:]:
        who = ""
        if e.agent_id:
            agent = next((a for a in store.list_agents() if a.id == e.agent_id), None)
            who = f"[{agent.name}] " if agent else ""
        print(f"  • {who}{e.message}")
    return len(events)


def main(argv: list[str]) -> int:
    goal = argv[1] if len(argv) > 1 else "Reduzir custos financeiros e renegociar compras"

    store = InMemoryStore()
    engine = SimulationEngine(store=store)

    print(f"\n🏢 Objetivo da empresa: {goal}\n")
    engine.start(goal)
    seen = _print_events(store, 0)

    engine.run_until_idle()
    seen = _print_events(store, seen)

    while store.list_pending_approvals() or store.list_pending_handoffs():
        # Aprovacoes: o agente fez, o presidente valida.
        for appr in store.list_pending_approvals():
            task = store.get_task(appr.task_id)
            agent = next(a for a in store.list_agents() if a.id == appr.agent_id)
            print(f"\n⏸️  [APROVACAO] {agent.name} quer '{task.title}' via {appr.tool}")
            engine.resolve_approval(appr.id, approved=True, decided_by="demo")

        # Handoffs: passo so'-humano; a pessoa executa/decide e devolve.
        for hand in store.list_pending_handoffs():
            task = store.get_task(hand.task_id)
            if hand.kind == "decision":
                escolha = hand.options[0] if hand.options else None
                print(f"\n🙋 [HUMANO DECIDE] '{task.title}' -> {escolha['label'] if escolha else 'n/a'}")
                engine.resolve_handoff(hand.id, chosen_branch_id=escolha["id"] if escolha else None,
                                       decided_by="demo")
            else:
                print(f"\n🙋 [HUMANO EXECUTA] '{task.title}'")
                engine.resolve_handoff(hand.id, result="Feito manualmente pela pessoa.",
                                       decided_by="demo")

        seen = _print_events(store, seen)
        engine.run_until_idle()
        seen = _print_events(store, seen)

    print(f"\n✅ Status final: {store.get_sim().status}")
    print(f"   Agentes ociosos: "
          f"{sum(1 for a in store.list_agents() if a.status == AgentStatus.IDLE)}"
          f"/{len(store.list_agents())}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
