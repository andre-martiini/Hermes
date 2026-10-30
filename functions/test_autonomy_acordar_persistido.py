"""Testes de `autonomy/acordar_persistido.py` (P08): despertar de espera externa persistido."""

import unittest
from datetime import datetime, timedelta, timezone

from autonomy import pedido_repositorio as repo
from autonomy.acordar_persistido import acordar_pedido
from autonomy.execution import LeaseInvalida
from autonomy.requests import RequestStatus
from autonomy.runs import AgentRunStatus
from test_autonomy_pedido_repositorio import _Db
from test_autonomy_runner_aplicacao import T0, TestAcordarEsperaExterna


class TestAcordarPedido(unittest.TestCase):
    def setUp(self):
        self.db = _Db()
        self.p = TestAcordarEsperaExterna()._esperando(T0 + timedelta(hours=1))
        repo.criar_pedido(self.db, self.p)
        self.caminho = f"req-1/{repo.SUBCOLECAO_RUNS_ENCERRADOS}/{self.p.run.run_id}"

    def test_acorda_e_persiste_pedido_e_run_antigo(self):
        r = acordar_pedido(self.db, "req-1", "ex-b", "run-2", agora=T0 + timedelta(hours=2))
        self.assertEqual(r.pedido.status, RequestStatus.EM_ANDAMENTO)
        self.assertEqual(r.pedido.run.run_id, "run-2")
        self.assertEqual(repo.ler_pedido(self.db, "req-1"), r.pedido)
        self.assertEqual(r.run_antigo.status, AgentRunStatus.TIMEOUT)
        gravado = self.db.docs[self.caminho]
        self.assertEqual(gravado["status"], AgentRunStatus.TIMEOUT.value)
        self.assertEqual(gravado["run_id"], self.p.run.run_id)

    def test_antes_do_horario_recusa_sem_gravar(self):
        with self.assertRaises(LeaseInvalida):
            acordar_pedido(self.db, "req-1", "ex-b", "run-2", agora=T0 + timedelta(minutes=10))
        self.assertEqual(set(self.db.docs), {"req-1"})
        self.assertEqual(self.db.docs["req-1"]["revisao"], 1)

    def test_por_evento_acorda_antes_do_horario(self):
        r = acordar_pedido(
            self.db, "req-1", "ex-b", "run-2", agora=T0 + timedelta(minutes=10), por_evento=True)
        self.assertEqual(r.pedido.status, RequestStatus.EM_ANDAMENTO)
        self.assertIn(self.caminho, self.db.docs)

    def test_segundo_despertar_nao_reabre_o_pedido(self):
        acordar_pedido(self.db, "req-1", "ex-b", "run-2", agora=T0 + timedelta(hours=2))
        with self.assertRaises(ValueError):
            acordar_pedido(self.db, "req-1", "ex-c", "run-3", agora=T0 + timedelta(hours=2))
        self.assertEqual(repo.ler_pedido(self.db, "req-1").run.run_id, "run-2")

    def test_run_id_invalido_recusa_antes_de_gravar(self):
        for ruim in ("a/b", "__x__", " r"):
            with self.assertRaises(ValueError):
                acordar_pedido(self.db, "req-1", "ex-b", ruim, agora=T0 + timedelta(hours=2))
        self.assertEqual(self.db.docs["req-1"]["revisao"], 1)

    def test_run_id_reutilizado_nao_sobrescreve_arquivo(self):
        self.db.docs[self.caminho] = {"run_id": "outro-conteudo"}
        with self.assertRaises(ValueError):
            acordar_pedido(self.db, "req-1", "ex-b", "run-2", agora=T0 + timedelta(hours=2))
        self.assertEqual(self.db.docs[self.caminho], {"run_id": "outro-conteudo"})
        self.assertEqual(self.db.docs["req-1"]["revisao"], 1)

    def test_inexistente_e_agora_sem_fuso(self):
        with self.assertRaises(repo.PedidoNaoEncontrado):
            acordar_pedido(self.db, "nao", "ex-b", "run-2", agora=T0)
        with self.assertRaises(ValueError):
            acordar_pedido(self.db, "req-1", "ex-b", "run-2", agora=datetime(2026, 10, 30))


if __name__ == "__main__":
    unittest.main()
