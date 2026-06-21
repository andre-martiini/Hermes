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

    pendentes = store.list_pending_approvals()
    while pendentes:
        print("\n⏸️  Acoes aguardando o PRESIDENTE (voce):")
        for appr in pendentes:
            task = store.get_task(appr.task_id)
            agent = next(a for a in store.list_agents() if a.id == appr.agent_id)
            print(f"   - {agent.name} quer '{task.title}' via {appr.tool}")
            # No demo, o presidente aprova tudo automaticamente.
            engine.resolve_approval(appr.id, approved=True, decided_by="demo")
        seen = _print_events(store, seen)
        engine.run_until_idle()
        seen = _print_events(store, seen)
        pendentes = store.list_pending_approvals()

    print(f"\n✅ Status final: {store.get_sim().status}")
    print(f"   Agentes ociosos: "
          f"{sum(1 for a in store.list_agents() if a.status == AgentStatus.IDLE)}"
          f"/{len(store.list_agents())}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
