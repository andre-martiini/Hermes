"""Testes de `autonomy/reconciliar_persistido.py` (P08): reconciliação de resultado desconhecido persistida."""

import dataclasses
import unittest
from datetime import datetime, timedelta

from autonomy import pedido_repositorio as repo
from autonomy.execution import LeaseInvalida
from autonomy.reconciliar_persistido import reconciliar_pedido
from autonomy.requests import RequestStatus
from autonomy.runs import AgentRunStatus
from test_autonomy_pedido_repositorio import _Db
from test_autonomy_runner_aplicacao import _desconhecido, _em_andamento


class TestReconciliarPedido(unittest.TestCase):
    def setUp(self):
        self.db = _Db()
        self.p, self.agora = _desconhecido()
        repo.criar_pedido(self.db, self.p)
        self.rid = self.p.request_id
        self.arq = f"{self.rid}/{repo.SUBCOLECAO_RUNS_ENCERRADOS}"

    def _com_run_ativo(self):
        """Pedido desconhecido cujo run ainda consta ativo (sweep não o fechou)."""
        ativo = _em_andamento()
        p = dataclasses.replace(
            ativo, status=RequestStatus.RESULTADO_DESCONHECIDO)
        db = _Db()
        repo.criar_pedido(db, p)
        return db, p, p.lease.expires_at + timedelta(minutes=1)

    def test_efeito_ocorreu_persiste_verificando(self):
        r = reconciliar_pedido(
            self.db, self.rid, True, agora=self.agora, executor_id="ex-b", run_id="run-2")
        self.assertEqual(r.pedido.status, RequestStatus.VERIFICANDO)
        self.assertEqual(r.pedido.run.run_id, "run-2")
        self.assertEqual(repo.ler_pedido(self.db, self.rid), r.pedido)
        # sweep já tinha fechado o run: ele é arquivado ao ser substituído pelo run do verificador
        self.assertEqual(r.run_antigo, self.p.run)
        self.assertEqual(self.db.docs[f"{self.arq}/{self.p.run.run_id}"]["run_id"], self.p.run.run_id)
        self.assertEqual(self.db.docs[self.rid]["revisao"], 2)

    def test_efeito_nao_ocorreu_persiste_retentativa(self):
        quando = self.agora + timedelta(minutes=10)
        r = reconciliar_pedido(self.db, self.rid, False, agora=self.agora, continuar_em=quando)
        self.assertEqual(r.pedido.status, RequestStatus.RETENTATIVA_AGENDADA)
        self.assertEqual(r.pedido.tentativas, self.p.tentativas + 1)
        self.assertEqual(repo.ler_pedido(self.db, self.rid), r.pedido)
        self.assertIsNone(r.run_antigo)  # run terminal permanece em pedido.run
        self.assertNotIn(f"{self.arq}/{self.p.run.run_id}", self.db.docs)

    def test_run_antigo_ativo_e_arquivado_na_mesma_transacao(self):
        db, p, agora = self._com_run_ativo()
        r = reconciliar_pedido(db, p.request_id, True, agora=agora, executor_id="ex-b", run_id="run-2")
        self.assertEqual(r.run_antigo.status, AgentRunStatus.TIMEOUT)
        gravado = db.docs[f"{p.request_id}/{repo.SUBCOLECAO_RUNS_ENCERRADOS}/{p.run.run_id}"]
        self.assertEqual(gravado["status"], AgentRunStatus.TIMEOUT.value)
        self.assertEqual(repo.ler_pedido(db, p.request_id).run.run_id, "run-2")

    def test_retentativa_com_run_ativo_tambem_arquiva(self):
        db, p, agora = self._com_run_ativo()
        r = reconciliar_pedido(
            db, p.request_id, False, agora=agora, continuar_em=agora + timedelta(minutes=5))
        self.assertEqual(r.pedido.status, RequestStatus.RETENTATIVA_AGENDADA)
        self.assertIn(f"{p.request_id}/{repo.SUBCOLECAO_RUNS_ENCERRADOS}/{p.run.run_id}", db.docs)

    def test_lease_valida_recusa_sem_gravar(self):
        with self.assertRaises(LeaseInvalida):
            reconciliar_pedido(
                self.db, self.rid, True, agora=self.p.lease.expires_at - timedelta(seconds=1),
                executor_id="ex-b", run_id="run-2")
        self.assertEqual(self.db.docs[self.rid]["revisao"], 1)

    def test_run_id_invalido_recusa_antes_de_gravar(self):
        for ruim in ("a/b", "__x__", " r", ""):
            with self.assertRaises(ValueError):
                reconciliar_pedido(
                    self.db, self.rid, True, agora=self.agora, executor_id="ex-b", run_id=ruim)
        self.assertEqual(self.db.docs[self.rid]["revisao"], 1)

    def test_run_id_novo_ja_arquivado_recusa_sem_gravar(self):
        self.db.docs[f"{self.arq}/run-2"] = {"run_id": "run-2"}
        with self.assertRaises(ValueError):
            reconciliar_pedido(
                self.db, self.rid, True, agora=self.agora, executor_id="ex-b", run_id="run-2")
        self.assertEqual(self.db.docs[self.rid]["revisao"], 1)

    def test_segunda_reconciliacao_nao_reabre(self):
        reconciliar_pedido(
            self.db, self.rid, True, agora=self.agora, executor_id="ex-b", run_id="run-2")
        with self.assertRaises(ValueError):
            reconciliar_pedido(
                self.db, self.rid, True, agora=self.agora, executor_id="ex-c", run_id="run-3")
        self.assertEqual(repo.ler_pedido(self.db, self.rid).run.run_id, "run-2")

    def test_retentativa_sem_continuar_em_recusa(self):
        with self.assertRaises(ValueError):
            reconciliar_pedido(self.db, self.rid, False, agora=self.agora)
        self.assertEqual(self.db.docs[self.rid]["revisao"], 1)

    def test_inexistente_e_agora_sem_fuso(self):
        with self.assertRaises(repo.PedidoNaoEncontrado):
            reconciliar_pedido(self.db, "nao", True, agora=self.agora, executor_id="e", run_id="r")
        with self.assertRaises(ValueError):
            reconciliar_pedido(
                self.db, self.rid, True, agora=datetime(2026, 10, 30), executor_id="e", run_id="r")


if __name__ == "__main__":
    unittest.main()
