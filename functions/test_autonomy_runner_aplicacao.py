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
from autonomy.runner_aplicacao import (
    acordar_espera_externa,
    aplicar_decisao_continuacao,
    reconciliar_resultado_desconhecido,
)
from autonomy.runner_continuacao import DecisaoContinuacao
from autonomy.runs import AgentRunStatus
from autonomy.sweep import varrer_espera_vencida

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


class TestAcordarEsperaExterna(unittest.TestCase):
    def _esperando(self, acordar_em=None):
        p = _em_andamento()
        return _aplicar(p, DecisaoContinuacao(
            RequestStatus.AGUARDANDO_EXTERNO, continuar_em=acordar_em, condicao_espera="resposta"))

    def test_acorda_com_lease_e_run_novos(self):
        p = self._esperando(T0 + timedelta(hours=1))
        agora = T0 + timedelta(hours=2)
        n, antigo = acordar_espera_externa(p, "ex-b", "run-2", agora)
        self.assertEqual(n.status, RequestStatus.EM_ANDAMENTO)
        self.assertEqual(n.lease.generation, p.lease.generation + 1)
        self.assertNotEqual(n.lease.lease_token, p.lease.lease_token)
        self.assertEqual(n.run.run_id, "run-2")
        self.assertEqual(n.run.status, AgentRunStatus.EM_ANDAMENTO)
        self.assertEqual(antigo.status, AgentRunStatus.TIMEOUT)
        self.assertEqual(n.condicao_espera, "")
        self.assertIsNone(n.proximo_tentativa_em)
        self.assertEqual(n.ledger_entry, p.ledger_entry)
        self.assertEqual((n.tentativas, n.pausas), (p.tentativas, p.pausas))

    def test_token_antigo_perde_o_fencing(self):
        p = self._esperando()
        n, _ = acordar_espera_externa(p, "ex-b", "run-2", T0 + timedelta(hours=1))
        with self.assertRaises(LeaseInvalida):
            registrar_progresso(
                n, p.lease.lease_token, p.lease.generation, "k2", {"a": 2}, {"passo": 2},
                agora=T0 + timedelta(hours=1))

    def test_antes_do_horario_recusa_exceto_por_evento(self):
        p = self._esperando(T0 + timedelta(hours=3))
        agora = T0 + timedelta(hours=1)
        with self.assertRaises(LeaseInvalida):
            acordar_espera_externa(p, "ex-b", "run-2", agora)
        n, _ = acordar_espera_externa(p, "ex-b", "run-2", agora, por_evento=True)
        self.assertEqual(n.status, RequestStatus.EM_ANDAMENTO)

    def test_lease_ainda_valida_recusa_mesmo_por_evento(self):
        p = self._esperando()
        with self.assertRaises(LeaseInvalida):
            acordar_espera_externa(p, "ex-b", "run-2", T0 + timedelta(seconds=1), por_evento=True)

    def test_status_errado_e_entradas_invalidas(self):
        em = _em_andamento()
        with self.assertRaises(ValueError):
            acordar_espera_externa(em, "ex-b", "run-2", T0 + timedelta(hours=1))
        p = self._esperando()
        with self.assertRaises(ValueError):
            acordar_espera_externa(p, "ex-b", "run-2", datetime(2026, 10, 28, 15))
        with self.assertRaises(ValueError):
            acordar_espera_externa(p, "ex-b", "run-2", T0 + timedelta(hours=1), por_evento="sim")
        with self.assertRaises(ValueError):
            acordar_espera_externa(p, "", "run-2", T0 + timedelta(hours=1))

    def test_run_id_repetido_recusa(self):
        p = self._esperando()
        with self.assertRaises(ValueError):
            acordar_espera_externa(p, "ex-b", p.run.run_id, T0 + timedelta(hours=1))
        with self.assertRaises(ValueError):
            acordar_espera_externa(p, "ex-b", f" {p.run.run_id} ", T0 + timedelta(hours=1))

    def test_sem_lease_recusa(self):
        p = dataclasses.replace(self._esperando(), lease=None)
        with self.assertRaises(LeaseInvalida):
            acordar_espera_externa(p, "ex-b", "run-2", T0 + timedelta(hours=1))

    def test_sem_run_antigo_devolve_none(self):
        p = dataclasses.replace(self._esperando(), run=None)
        n, antigo = acordar_espera_externa(p, "ex-b", "run-2", T0 + timedelta(hours=1))
        self.assertIsNone(antigo)
        self.assertEqual(n.run.run_id, "run-2")

    def test_pode_voltar_a_esperar_depois_de_acordar(self):
        p = self._esperando()
        n, _ = acordar_espera_externa(p, "ex-b", "run-2", T0 + timedelta(hours=1))
        de_novo = _aplicar(n, DecisaoContinuacao(
            RequestStatus.AGUARDANDO_EXTERNO, condicao_espera="outra"), agora=T0 + timedelta(hours=1))
        self.assertEqual(de_novo.status, RequestStatus.AGUARDANDO_EXTERNO)


def _desconhecido():
    p = _em_andamento()
    p = aplicar_decisao_continuacao(
        p, p.lease.lease_token, p.lease.generation,
        DecisaoContinuacao(RequestStatus.VERIFICANDO, motivo="v"), T0)
    depois = p.lease.expires_at + timedelta(minutes=1)
    return varrer_espera_vencida(p, agora=depois).pedido, depois


class TestReconciliarDesconhecido(unittest.TestCase):
    def test_efeito_ocorreu_vai_a_verificando_com_lease_e_run_novos(self):
        p, agora = _desconhecido()
        n, antigo = reconciliar_resultado_desconhecido(
            p, True, agora, executor_id="ex-b", run_id="run-2")
        self.assertEqual(n.status, RequestStatus.VERIFICANDO)
        self.assertEqual(n.lease.generation, p.lease.generation + 1)
        self.assertEqual(n.run.run_id, "run-2")
        self.assertEqual(n.ledger_entry, p.ledger_entry)
        self.assertEqual(n.tentativas, p.tentativas)
        self.assertIsNone(antigo)  # sweep já fechou o run antigo

    def test_efeito_nao_ocorreu_agenda_retentativa(self):
        p, agora = _desconhecido()
        quando = agora + timedelta(minutes=10)
        n, _ = reconciliar_resultado_desconhecido(p, False, agora, continuar_em=quando)
        self.assertEqual(n.status, RequestStatus.RETENTATIVA_AGENDADA)
        self.assertEqual(n.tentativas, p.tentativas + 1)
        self.assertEqual(n.proximo_tentativa_em, quando)
        self.assertTrue(lease_expirada(n.lease, agora=agora))

    def test_retentativa_exige_continuar_em_futuro(self):
        p, agora = _desconhecido()
        for q in (None, agora, agora - timedelta(seconds=1), datetime(2026, 11, 1)):
            with self.assertRaises(ValueError):
                reconciliar_resultado_desconhecido(p, False, agora, continuar_em=q)

    def test_verificar_exige_ids_e_run_novo(self):
        p, agora = _desconhecido()
        with self.assertRaises(ValueError):
            reconciliar_resultado_desconhecido(p, True, agora)
        with self.assertRaises(ValueError):
            reconciliar_resultado_desconhecido(
                p, True, agora, executor_id="ex-b", run_id=p.run.run_id)

    def test_recusa_lease_valida_e_status_errado(self):
        p, agora = _desconhecido()
        with self.assertRaises(LeaseInvalida):
            reconciliar_resultado_desconhecido(
                p, True, p.lease.expires_at - timedelta(seconds=1),
                executor_id="ex-b", run_id="run-2")
        with self.assertRaises(ValueError):
            reconciliar_resultado_desconhecido(
                _em_andamento(), True, agora, executor_id="ex-b", run_id="run-2")

    def test_validacoes_de_tipo(self):
        p, agora = _desconhecido()
        with self.assertRaises(ValueError):
            reconciliar_resultado_desconhecido(p, 1, agora, executor_id="e", run_id="r")
        with self.assertRaises(ValueError):
            reconciliar_resultado_desconhecido(p, True, datetime(2026, 11, 1), executor_id="e", run_id="r")
        with self.assertRaises(ValueError):
            reconciliar_resultado_desconhecido("x", True, agora)

    def test_run_ativo_e_fechado_por_timeout_e_devolvido(self):
        p, agora = _desconhecido()
        ativo = dataclasses.replace(
            p, run=_em_andamento().run)  # run ainda ativo (inconsistência tolerada)
        n, antigo = reconciliar_resultado_desconhecido(
            ativo, True, agora, executor_id="ex-b", run_id="run-9")
        self.assertIsNotNone(antigo)
        self.assertFalse(antigo.status == AgentRunStatus.EM_ANDAMENTO)

    def test_retentativa_respeita_teto_de_tentativas(self):
        from autonomy.requests import DEFAULT_MAX_TENTATIVAS
        p, agora = _desconhecido()
        p = dataclasses.replace(p, tentativas=DEFAULT_MAX_TENTATIVAS)
        with self.assertRaises(ValueError):
            reconciliar_resultado_desconhecido(
                p, False, agora, continuar_em=agora + timedelta(days=1))
        ok, _ = reconciliar_resultado_desconhecido(
            dataclasses.replace(p, tentativas=DEFAULT_MAX_TENTATIVAS - 1), False, agora,
            continuar_em=agora + timedelta(days=1))
        self.assertEqual(ok.tentativas, DEFAULT_MAX_TENTATIVAS)
