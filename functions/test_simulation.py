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

    def test_agent_decides_branch_and_prunes_the_other(self):
        # "decidir" gera um no' de decisao com dois ramos (sem acao sensivel concorrente).
        self.engine.start("Decidir a estrategia geral")
        self.engine.run_until_idle()
        # O agente decidiu sozinho (no' nao-critico): nada parou para humano.
        self.assertFalse(self.store.list_pending_handoffs())
        types_seen = {e.type for e in self.store.list_events()}
        self.assertIn("decision_made", types_seen)
        self.assertIn("branch_pruned", types_seen)
        # Exatamente um ramo concluido e um podado.
        ramos = [t for t in self.store.list_tasks() if t.title.startswith("Caminho")]
        self.assertEqual(len(ramos), 2)
        self.assertEqual(sorted(t.status for t in ramos),
                         sorted([TaskStatus.DONE, TaskStatus.SKIPPED]))

    def test_human_only_step_creates_handoff_and_pauses(self):
        # "assinar contrato" => passo so'-humano (handoff de trabalho), sem acao sensivel.
        self.engine.start("Assinar o contrato final")
        self.engine.run_until_idle()
        handoffs = self.store.list_pending_handoffs()
        self.assertTrue(len(handoffs) >= 1)
        hand = handoffs[0]
        self.assertEqual(hand.kind, "work")
        task = self.store.get_task(hand.task_id)
        self.assertEqual(task.status, TaskStatus.AWAITING_HUMAN)
        self.assertNotEqual(self.store.get_sim().status, SimStatus.DONE)

        # A pessoa faz e devolve o resultado; o fluxo retoma e fecha.
        self.engine.resolve_handoff(hand.id, result="Contrato assinado em 21/06.")
        self.engine.run_until_idle()
        self.assertEqual(self.store.get_task(hand.task_id).status, TaskStatus.DONE)
        self.assertEqual(self.store.get_sim().status, SimStatus.DONE)

    def test_critical_decision_requires_human(self):
        # decisao + contexto juridico => no' critico: SO' humano escolhe o ramo.
        self.engine.start("Decidir juridicamente e assinar a renegociacao do contrato")
        self.engine.run_until_idle()
        decision_handoffs = [h for h in self.store.list_pending_handoffs()
                             if h.kind == "decision"]
        self.assertTrue(len(decision_handoffs) >= 1,
                        "no' de decisao critico deveria virar handoff de decisao")
        hand = decision_handoffs[0]
        # Humano escolhe o segundo ramo.
        escolha = hand.options[1]
        self.engine.resolve_handoff(hand.id, chosen_branch_id=escolha["id"])
        self.engine.run_until_idle()
        decision_task = self.store.get_task(hand.task_id)
        self.assertEqual(decision_task.status, TaskStatus.DONE)
        self.assertEqual(decision_task.chosen_branch_id, escolha["id"])

    def test_start_from_action_uses_action_plan(self):
        action = {
            "id": "tarefa_real_123",
            "titulo": "Organizar evento de fim de ano",
            "descricao": "Planejar e executar a confraternizacao",
            "plano_de_acao": [
                {"text": "Levantar orcamento financeiro do evento", "completed": False},
                {"text": "Comprar materiais e itens de decoracao", "completed": False},
                {"text": "Assinar o contrato com o buffet", "completed": False},
            ],
        }
        sim = self.engine.start_from_action(action)
        self.assertEqual(sim.source_action_id, "tarefa_real_123")
        # Cada passo do plano virou uma tarefa (+ consolidacao).
        titulos = [t.title for t in self.store.list_tasks()]
        self.assertIn("Levantar orcamento financeiro do evento", titulos)
        # O passo de assinatura nasceu como handoff humano.
        self.engine.run_until_idle()
        human_steps = [t for t in self.store.list_tasks()
                       if t.executor_type == "human"]
        self.assertTrue(len(human_steps) >= 1)


if __name__ == "__main__":
    unittest.main()
