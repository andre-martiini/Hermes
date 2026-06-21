"""Ambiente paralelo de simulacao de empresa do Hermes.

Este pacote modela uma "empresa de agentes" que opera SOMENTE dentro de um
namespace isolado (`simulation/`), sem nunca tocar nos dados reais de producao.

Camadas:
- models.py        -> estruturas de dados (Agente, Tarefa, Evento, Aprovacao, Simulacao)
- roles.py         -> setores/papeis e o roster padrao da empresa
- store.py         -> persistencia (InMemory para testes; Firestore com prefixo travado)
- orchestrator.py  -> o "CEO": decompoe um objetivo em tarefas por setor
- engine.py        -> o loop de execucao (atribuicao, gating de aprovacao, eventos)

A camada grafica (o "escritorio" com os bonequinhos) e' construida por cima do
stream de eventos (`SimEvent`) emitido pelo engine.
"""

from .models import (
    Agent,
    Approval,
    SimEvent,
    Simulation,
    Task,
    AgentStatus,
    TaskStatus,
    ApprovalStatus,
)
from .roles import Sector, default_company
from .engine import SimulationEngine
from .store import InMemoryStore, SimulationStore

__all__ = [
    "Agent",
    "Approval",
    "SimEvent",
    "Simulation",
    "Task",
    "AgentStatus",
    "TaskStatus",
    "ApprovalStatus",
    "Sector",
    "default_company",
    "SimulationEngine",
    "InMemoryStore",
    "SimulationStore",
]
