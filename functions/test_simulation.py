"""Teste end-to-end da simulacao de empresa (offline, sem credenciais).

Demonstra o ciclo completo:
  objetivo -> plano por setor -> execucao -> PARADA para aprovacao do presidente
  -> aprovacao humana -> execucao -> conclusao.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from simulation import SimulationEngine, InMemoryStore
from simulation.models import AgentStatus, ApprovalStatus, SimStatus, TaskStatus


class TestSimulationEngine(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStore()
        self.engine = SimulationEngine(store=self.store)

    def test_planning_creates_tasks_and_roster(self):
        self.engine.start("Reduzir custos financeiros e renegociar compras")
        self.assertTrue(len(self.store.list_agents()) >= 2)
        tasks = self.store.list_tasks()
        self.assertTrue(len(tasks) >= 2)
        # A Diretoria sempre fecha com a consolidacao.
        self.assertTrue(any(t.sector == "DIRETORIA" for t in tasks))

    def test_sensitive_action_pauses_for_approval(self):
        self.engine.start("Registrar uma nova despesa financeira no orcamento")
        self.engine.run_until_idle()

        pendentes = self.store.list_pending_approvals()
        self.assertTrue(len(pendentes) >= 1,
                        "Acao financeira sensivel deveria gerar aprovacao pendente")

        # O agente responsavel ficou esperando o presidente.
        appr = pendentes[0]
        task = self.store.get_task(appr.task_id)
        self.assertEqual(task.status, TaskStatus.AWAITING_APPROVAL)
        agent = next(a for a in self.store.list_agents() if a.id == appr.agent_id)
        self.assertEqual(agent.status, AgentStatus.WAITING_APPROVAL)

        # A simulacao NAO terminou: esta' bloqueada aguardando decisao humana.
        self.assertNotEqual(self.store.get_sim().status, SimStatus.DONE)

    def test_human_approval_unblocks_and_completes(self):
        self.engine.start("Registrar uma nova despesa financeira no orcamento")
        self.engine.run_until_idle()

        appr = self.store.list_pending_approvals()[0]
        self.engine.resolve_approval(appr.id, approved=True, decided_by="andre")
        self.engine.run_until_idle()

        # Aprovacao consumida, tarefa concluida, agente liberado.
        self.assertEqual(self.store.get_approval(appr.id).status, ApprovalStatus.APPROVED)
        task = self.store.get_task(appr.task_id)
        self.assertEqual(task.status, TaskStatus.DONE)
        self.assertEqual(self.store.get_sim().status, SimStatus.DONE)

    def test_rejection_marks_task_rejected(self):
        self.engine.start("Registrar uma nova despesa financeira no orcamento")
        self.engine.run_until_idle()
        appr = self.store.list_pending_approvals()[0]
        self.engine.resolve_approval(appr.id, approved=False, reason="fora do orcamento")
        task = self.store.get_task(appr.task_id)
        self.assertEqual(task.status, TaskStatus.REJECTED)

    def test_events_are_emitted_for_graphical_layer(self):
        self.engine.start("Pesquisar mercado e preparar comunicacao por whatsapp")
        self.engine.run_until_idle()
        types_seen = {e.type for e in self.store.list_events()}
        self.assertIn("sim_started", types_seen)
        self.assertIn("plan_ready", types_seen)
        self.assertIn("agent_assigned", types_seen)


if __name__ == "__main__":
    unittest.main()
