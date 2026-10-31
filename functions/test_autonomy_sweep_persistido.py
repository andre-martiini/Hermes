"""Testes de `autonomy/sweep_persistido.py` (P08): sweep de um pedido com persistência."""

import dataclasses
import unittest
from datetime import datetime, timedelta, timezone

from autonomy import pedido_repositorio as repo
from autonomy import sweep_persistido as sp
from autonomy.execution import PedidoDuravel, assumir_pedido, registrar_progresso
from autonomy.requests import RequestStatus
from test_autonomy_pedido_repositorio import _Db

T0 = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def _em_andamento():
    p = assumir_pedido(PedidoDuravel("req-1", RequestStatus.PENDENTE), "ex-a", "run-1", agora=T0)
    return registrar_progresso(p, p.lease.lease_token, p.lease.generation, "k1", {"a": 1}, {"n": 1}, agora=T0)


class TestSweepPersistido(unittest.TestCase):
    def setUp(self):
        self.db = _Db()

    def _criar(self, pedido):
        repo.criar_pedido(self.db, pedido)

    def test_lease_vencida_agenda_retentativa_e_grava(self):
        p = _em_andamento()
        self._criar(p)
        r = sp.varrer_pedido(self.db, "req-1", agora=p.lease.expires_at + timedelta(seconds=1))
        self.assertEqual(r.acao, "lease_vencida")
        self.assertEqual(r.pedido.status, RequestStatus.RETENTATIVA_AGENDADA)
        self.assertEqual(repo.ler_pedido(self.db, "req-1"), r.pedido)
        self.assertEqual(self.db.docs["req-1"]["revisao"], 2)

    def test_lease_valida_nao_escreve(self):
        p = _em_andamento()
        self._criar(p)
        r = sp.varrer_pedido(self.db, "req-1", agora=T0)
        self.assertIsNone(r.acao)
        self.assertEqual(r.pedido, p)
        self.assertEqual(self.db.docs["req-1"]["revisao"], 1)

    def test_tentativas_esgotadas_devolve_diagnostico(self):
        p = dataclasses.replace(_em_andamento(), tentativas=3)
        self._criar(p)
        r = sp.varrer_pedido(
            self.db, "req-1", agora=p.lease.expires_at + timedelta(seconds=1), max_tentativas=3
        )
        self.assertEqual(r.pedido.status, RequestStatus.FALHA_FINAL)
        self.assertIsNotNone(r.diagnostico)
        self.assertEqual(r.diagnostico.request_id, "req-1")

    def test_retentativa_pronta_vira_pendente_e_ainda_nao_pronta_nao_escreve(self):
        p = dataclasses.replace(
            PedidoDuravel("req-1", RequestStatus.RETENTATIVA_AGENDADA),
            proximo_tentativa_em=T0 + timedelta(minutes=5),
            tentativas=1,
        )
        self._criar(p)
        cedo = sp.varrer_pedido(self.db, "req-1", agora=T0)
        self.assertIsNone(cedo.acao)
        self.assertEqual(self.db.docs["req-1"]["revisao"], 1)
        pronto = sp.varrer_pedido(self.db, "req-1", agora=T0 + timedelta(minutes=5))
        self.assertEqual(pronto.acao, "retentativa_promovida")
        self.assertEqual(pronto.pedido.status, RequestStatus.PENDENTE)
        self.assertIsNone(pronto.pedido.proximo_tentativa_em)

    def test_status_sem_varredura_nao_escreve(self):
        self._criar(PedidoDuravel("req-1", RequestStatus.PENDENTE))
        r = sp.varrer_pedido(self.db, "req-1", agora=T0)
        self.assertIsNone(r.acao)
        self.assertEqual(self.db.docs["req-1"]["revisao"], 1)

    def test_espera_externa_vencida_vira_resultado_desconhecido(self):
        p = dataclasses.replace(
            _em_andamento(),
            status=RequestStatus.AGUARDANDO_EXTERNO,
            condicao_espera="resposta",
            proximo_tentativa_em=T0 + timedelta(minutes=1),
        )
        self._criar(p)
        # lease vencida mas ainda dentro da espera: normal, nada a varrer
        antes = T0 + timedelta(seconds=30)
        venc = max(p.lease.expires_at, T0 + timedelta(minutes=2))
        if p.lease.expires_at <= antes:
            p = dataclasses.replace(p, lease=dataclasses.replace(p.lease, expires_at=T0 + timedelta(minutes=10)))
        self.assertIsNone(sp.decidir_varredura(p, antes))
        r = sp.varrer_pedido(self.db, "req-1", agora=venc + timedelta(minutes=20))
        self.assertEqual(r.acao, "espera_vencida")
        self.assertEqual(r.pedido.status, RequestStatus.RESULTADO_DESCONHECIDO)
        self.assertIsNotNone(r.diagnostico)

    def test_espera_e_verificacao_sem_lease_sobem_sem_gravar(self):
        # Contrato de varrer_espera_vencida (validado): sem lease não há o que varrer.
        for status in (RequestStatus.AGUARDANDO_EXTERNO, RequestStatus.VERIFICANDO):
            db = _Db()
            repo.criar_pedido(db, PedidoDuravel("r", status, condicao_espera="x"))
            with self.assertRaises(ValueError):
                sp.varrer_pedido(db, "r", agora=T0)
            self.assertEqual(db.docs["r"]["revisao"], 1)

    def test_agora_naive_recusado_e_inexistente_sobe(self):
        with self.assertRaises(ValueError):
            sp.varrer_pedido(self.db, "req-1", agora=datetime(2026, 10, 29, 12, 0))
        with self.assertRaises(repo.PedidoNaoEncontrado):
            sp.varrer_pedido(self.db, "nao-existe", agora=T0)

    def test_estado_incoerente_sobe_sem_gravar(self):
        p = dataclasses.replace(PedidoDuravel("req-1", RequestStatus.RETENTATIVA_AGENDADA))
        self._criar(p)
        with self.assertRaises(ValueError):
            sp.varrer_pedido(self.db, "req-1", agora=T0)
        self.assertEqual(self.db.docs["req-1"]["revisao"], 1)


if __name__ == "__main__":
    unittest.main()
