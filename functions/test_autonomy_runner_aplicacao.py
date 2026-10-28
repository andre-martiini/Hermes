"""Testes de `autonomy/runner_aplicacao.py` (P08): decisão -> pedido, puro."""

import dataclasses
import unittest
from datetime import datetime, timedelta, timezone

from autonomy.execution import (
    LeaseInvalida,
    PedidoDuravel,
    assumir_pedido,
    registrar_progresso,
)
from autonomy.requests import RequestStatus, lease_expirada
from autonomy.runner_aplicacao import aplicar_decisao_continuacao
from autonomy.runner_continuacao import DecisaoContinuacao
from autonomy.runs import AgentRunStatus

T0 = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)


def _em_andamento(com_ledger=True):
    p = assumir_pedido(PedidoDuravel("req-1", RequestStatus.PENDENTE), "ex-a", "run-1", agora=T0)
    if com_ledger:
        p = registrar_progresso(
            p, p.lease.lease_token, p.lease.generation, "k1", {"a": 1}, {"passo": 1}, agora=T0
        )
    else:
        p = dataclasses.replace(p, status=RequestStatus.EM_ANDAMENTO)
    return p


def _aplicar(p, dec, token=None, gen=None, agora=T0):
    return aplicar_decisao_continuacao(
        p, token or p.lease.lease_token, gen or p.lease.generation, dec, agora
    )


class TestAplicarDecisao(unittest.TestCase):
    def test_verificando_mantem_lease_e_run(self):
        p = _em_andamento()
        n = _aplicar(p, DecisaoContinuacao(RequestStatus.VERIFICANDO, motivo="ok"))
        self.assertEqual(n.status, RequestStatus.VERIFICANDO)
        self.assertEqual(n.lease, p.lease)
        self.assertEqual(n.run, p.run)

    def test_aguardando_externo_guarda_condicao_e_horario(self):
        p = _em_andamento()
        acordar = T0 + timedelta(hours=2)
        n = _aplicar(p, DecisaoContinuacao(
            RequestStatus.AGUARDANDO_EXTERNO, continuar_em=acordar, condicao_espera="resposta do fornecedor"))
        self.assertEqual(n.status, RequestStatus.AGUARDANDO_EXTERNO)
        self.assertEqual(n.proximo_tentativa_em, acordar)
        self.assertEqual(n.condicao_espera, "resposta do fornecedor")
        self.assertEqual(n.lease, p.lease)

    def test_aguardando_sem_condicao_rejeitado(self):
        with self.assertRaises(ValueError):
            _aplicar(_em_andamento(), DecisaoContinuacao(RequestStatus.AGUARDANDO_EXTERNO))

    def test_retentativa_libera_lease_fecha_run_e_grava_contadores(self):
        p = _em_andamento()
        quando = T0 + timedelta(seconds=60)
        n = _aplicar(p, DecisaoContinuacao(
            RequestStatus.RETENTATIVA_AGENDADA, continuar_em=quando, tentativas=2, pausas=1, motivo="429"))
        self.assertEqual(n.status, RequestStatus.RETENTATIVA_AGENDADA)
        self.assertEqual((n.tentativas, n.pausas), (2, 1))
        self.assertEqual(n.proximo_tentativa_em, quando)
        self.assertTrue(lease_expirada(n.lease, agora=T0))
        self.assertEqual(n.lease.generation, p.lease.generation)
        self.assertEqual(n.run.status, AgentRunStatus.FALHA)

    def test_retentativa_pode_ser_reassumida_na_hora(self):
        p = _em_andamento()
        quando = T0 + timedelta(seconds=60)
        n = _aplicar(p, DecisaoContinuacao(RequestStatus.RETENTATIVA_AGENDADA, continuar_em=quando, tentativas=1))
        r = assumir_pedido(n, "ex-b", "run-2", agora=quando)
        self.assertEqual(r.status, RequestStatus.RESERVADO)
        self.assertEqual(r.lease.generation, 2)

    def test_retentativa_sem_horario_rejeitada(self):
        with self.assertRaises(ValueError):
            _aplicar(_em_andamento(), DecisaoContinuacao(RequestStatus.RETENTATIVA_AGENDADA))

    def test_falha_final_sela_ledger_e_fecha_run(self):
        p = _em_andamento()
        n = _aplicar(p, DecisaoContinuacao(RequestStatus.FALHA_FINAL, tentativas=3, motivo="tentativas_esgotadas"))
        self.assertEqual(n.status, RequestStatus.FALHA_FINAL)
        self.assertEqual(n.tentativas, 3)
        self.assertIsNotNone(n.ledger_entry.resultado_registrado_em)
        self.assertEqual(n.run.status, AgentRunStatus.FALHA)

    def test_falha_final_sem_ledger(self):
        p = _em_andamento(com_ledger=False)
        n = _aplicar(p, DecisaoContinuacao(RequestStatus.FALHA_FINAL, motivo="recusa"))
        self.assertEqual(n.status, RequestStatus.FALHA_FINAL)
        self.assertEqual(n.run.status, AgentRunStatus.FALHA)

    def test_fencing_token_errado(self):
        with self.assertRaises(LeaseInvalida):
            _aplicar(_em_andamento(), DecisaoContinuacao(RequestStatus.VERIFICANDO), token="x")

    def test_fencing_geracao_errada(self):
        p = _em_andamento()
        with self.assertRaises(LeaseInvalida):
            _aplicar(p, DecisaoContinuacao(RequestStatus.VERIFICANDO), gen=p.lease.generation + 1)

    def test_lease_expirada_rejeitada(self):
        with self.assertRaises(LeaseInvalida):
            _aplicar(_em_andamento(), DecisaoContinuacao(RequestStatus.VERIFICANDO), agora=T0 + timedelta(hours=1))

    def test_pedido_fora_de_em_andamento_rejeitado(self):
        p = assumir_pedido(PedidoDuravel("r", RequestStatus.PENDENTE), "e", "run", agora=T0)
        with self.assertRaises(ValueError):
            _aplicar(p, DecisaoContinuacao(RequestStatus.VERIFICANDO))

    def test_status_nao_aplicavel_e_tipos_invalidos(self):
        p = _em_andamento()
        for dec in (DecisaoContinuacao(RequestStatus.CONCLUIDO), DecisaoContinuacao(RequestStatus.PENDENTE), "x", None):
            with self.assertRaises(ValueError):
                _aplicar(p, dec)
        with self.assertRaises(ValueError):
            _aplicar(p, DecisaoContinuacao(RequestStatus.VERIFICANDO), agora=datetime(2026, 1, 1))
        with self.assertRaises(ValueError):
            _aplicar(p, DecisaoContinuacao(RequestStatus.VERIFICANDO, tentativas=-1))

    def test_pausas_negativas_no_pedido_rejeitadas(self):
        with self.assertRaises(ValueError):
            PedidoDuravel("r", RequestStatus.PENDENTE, pausas=-1)

    def test_status_string_crua_rejeitado(self):
        p = _em_andamento()
        for st in ("retentativa_agendada", "falha_final", "verificando"):
            with self.assertRaises(ValueError):
                _aplicar(p, DecisaoContinuacao(st, continuar_em=T0 + timedelta(seconds=60)))

    def test_contadores_nao_regridem(self):
        p = dataclasses.replace(_em_andamento(), tentativas=2, pausas=3)
        with self.assertRaises(ValueError):
            _aplicar(p, DecisaoContinuacao(RequestStatus.VERIFICANDO, tentativas=0, pausas=3))
        with self.assertRaises(ValueError):
            _aplicar(p, DecisaoContinuacao(RequestStatus.VERIFICANDO, tentativas=2, pausas=0))

    def test_continuar_em_invalido(self):
        for v in ("amanha", datetime(2026, 1, 1)):
            with self.assertRaises(ValueError):
                _aplicar(_em_andamento(), DecisaoContinuacao(
                    RequestStatus.AGUARDANDO_EXTERNO, continuar_em=v, condicao_espera="x"))

    def test_retomar_espera_limpa_condicao(self):
        p = _em_andamento()
        w = _aplicar(p, DecisaoContinuacao(RequestStatus.AGUARDANDO_EXTERNO, condicao_espera="x"))
        r = registrar_progresso(w, w.lease.lease_token, w.lease.generation, "k1", {"a": 1}, {"passo": 2}, agora=T0)
        self.assertEqual(r.condicao_espera, "")


if __name__ == "__main__":
    unittest.main()
