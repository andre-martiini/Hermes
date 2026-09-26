"""Testes de `autonomy/sweep.py` -- só lógica pura, sem I/O (P04 sub-entrega
6/N: "criar sweep de leases vencidos, resultado desconhecido, retry agendado
e falha final, com fila de diagnóstico" do plano de autonomia, passo 7 do
pacote -- escopo desta fatia restrito a leases vencidas em
`RESERVADO`/`EM_ANDAMENTO` e à promoção de retentativa agendada; ver
docstring do módulo para o que fica de fora).
"""

import random
import unittest
from datetime import datetime, timedelta, timezone

from autonomy.execution import PedidoDuravel, assumir_pedido, registrar_progresso
from autonomy.requests import BACKOFF_BASE_SEGUNDOS, RequestStatus
from autonomy.runs import AgentRunStatus
from autonomy.sweep import (
    DiagnosticoPedido,
    promover_retentativa_pronta,
    varrer_lease_vencida,
)

T0 = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)


class _SemJitter:
    """Fake de `rng` para `autonomy.requests.calcular_backoff_segundos` --
    `.uniform(a, b)` sempre devolve 0.0, isolando o patamar EXATO escolhido
    (`BACKOFF_BASE_SEGUNDOS[indice]`) do jitter aleatório de +-20%."""

    def uniform(self, a: float, b: float) -> float:
        return 0.0


def _pedido_pendente(request_id: str = "req-1") -> PedidoDuravel:
    return PedidoDuravel(request_id=request_id, status=RequestStatus.PENDENTE)


def _pedido_reservado(request_id: str = "req-1", **kwargs) -> PedidoDuravel:
    pedido = assumir_pedido(_pedido_pendente(request_id), "executor-a", "run-1", agora=T0)
    if kwargs:
        pedido = _com_campos(pedido, **kwargs)
    return pedido


def _pedido_em_andamento(request_id: str = "req-1", **kwargs) -> PedidoDuravel:
    reservado = _pedido_reservado(request_id)
    pedido = registrar_progresso(
        reservado,
        reservado.lease.lease_token,
        reservado.lease.generation,
        idempotency_key="chave-1",
        payload={"a": 1},
        checkpoint_dados={"passo": 1},
        agora=T0,
    )
    if kwargs:
        pedido = _com_campos(pedido, **kwargs)
    return pedido


def _com_campos(pedido: PedidoDuravel, **kwargs) -> PedidoDuravel:
    import dataclasses

    return dataclasses.replace(pedido, **kwargs)


class TestVarrerLeaseVencidaValidacoes(unittest.TestCase):
    def test_status_nao_tratado_rejeitado(self):
        pedido = PedidoDuravel(request_id="req-1", status=RequestStatus.VERIFICANDO)
        with self.assertRaises(ValueError):
            varrer_lease_vencida(pedido, agora=T0)

    def test_pendente_rejeitado(self):
        with self.assertRaises(ValueError):
            varrer_lease_vencida(_pedido_pendente(), agora=T0)

    def test_sem_lease_rejeitado(self):
        pedido = PedidoDuravel(request_id="req-1", status=RequestStatus.EM_ANDAMENTO)
        with self.assertRaises(ValueError):
            varrer_lease_vencida(pedido, agora=T0)

    def test_lease_ainda_valida_rejeitada(self):
        pedido = _pedido_reservado()
        with self.assertRaises(ValueError):
            varrer_lease_vencida(pedido, agora=T0 + timedelta(seconds=1))


class TestVarrerLeaseVencidaReservado(unittest.TestCase):
    def test_reservado_sem_progresso_volta_a_pendente(self):
        pedido = _pedido_reservado()
        agora = T0 + timedelta(minutes=10)
        resultado = varrer_lease_vencida(pedido, agora=agora)
        self.assertEqual(resultado.pedido.status, RequestStatus.PENDENTE)
        self.assertIsNone(resultado.diagnostico)
        # Nenhum progresso foi feito, mas ainda CONTA como tentativa (achado
        # de revisão adversarial: sem contar aqui, um executor que trava
        # logo após cada reserva nunca esgotaria o limite -- ver docstring
        # de varrer_lease_vencida).
        self.assertEqual(resultado.pedido.tentativas, 1)
        self.assertIsNone(resultado.pedido.proximo_tentativa_em)

    def test_reservado_fecha_run_por_timeout(self):
        pedido = _pedido_reservado()
        agora = T0 + timedelta(minutes=10)
        resultado = varrer_lease_vencida(pedido, agora=agora)
        self.assertEqual(resultado.pedido.run.status, AgentRunStatus.TIMEOUT)
        self.assertEqual(resultado.pedido.run.finalizado_em, agora)

    def test_reservado_esgota_tentativas_cancela_com_diagnostico(self):
        # Executor que trava/cai IMEDIATAMENTE após cada reserva, sem nunca
        # progredir -- o ciclo PENDENTE -> RESERVADO -> (lease morre) -> ...
        # precisa de um teto, mesmo sem nenhum efeito parcial nunca ter
        # ocorrido (achado de revisão adversarial, 1a rodada).
        pedido = _pedido_reservado(tentativas=2)  # próxima seria a 3a (== max default)
        agora = T0 + timedelta(minutes=10)
        resultado = varrer_lease_vencida(pedido, agora=agora, max_tentativas=3)
        self.assertEqual(resultado.pedido.status, RequestStatus.CANCELADO)
        self.assertIsNone(resultado.pedido.proximo_tentativa_em)
        self.assertIsInstance(resultado.diagnostico, DiagnosticoPedido)
        self.assertEqual(resultado.diagnostico.tentativas, 3)
        self.assertEqual(resultado.diagnostico.status_anterior, RequestStatus.RESERVADO)


class TestVarrerLeaseVencidaEmAndamento(unittest.TestCase):
    def test_primeira_lease_vencida_agenda_retentativa(self):
        pedido = _pedido_em_andamento()
        agora = T0 + timedelta(minutes=10)
        resultado = varrer_lease_vencida(pedido, agora=agora, rng=random.Random(1))
        self.assertEqual(resultado.pedido.status, RequestStatus.RETENTATIVA_AGENDADA)
        self.assertIsNone(resultado.diagnostico)
        self.assertEqual(resultado.pedido.tentativas, 1)
        self.assertIsNotNone(resultado.pedido.proximo_tentativa_em)
        self.assertGreater(resultado.pedido.proximo_tentativa_em, agora)

    def test_em_andamento_fecha_run_por_timeout(self):
        pedido = _pedido_em_andamento()
        agora = T0 + timedelta(minutes=10)
        resultado = varrer_lease_vencida(pedido, agora=agora, rng=random.Random(1))
        self.assertEqual(resultado.pedido.run.status, AgentRunStatus.TIMEOUT)

    def test_esgota_tentativas_vai_para_falha_final_com_diagnostico(self):
        pedido = _pedido_em_andamento(tentativas=2)  # próxima seria a 3a (== max default)
        agora = T0 + timedelta(minutes=10)
        resultado = varrer_lease_vencida(pedido, agora=agora, max_tentativas=3)
        self.assertEqual(resultado.pedido.status, RequestStatus.FALHA_FINAL)
        self.assertIsNone(resultado.pedido.proximo_tentativa_em)
        self.assertIsInstance(resultado.diagnostico, DiagnosticoPedido)
        self.assertEqual(resultado.diagnostico.request_id, pedido.request_id)
        self.assertEqual(resultado.diagnostico.tentativas, 3)
        self.assertEqual(resultado.diagnostico.status_anterior, RequestStatus.EM_ANDAMENTO)
        self.assertEqual(resultado.diagnostico.registrado_em, agora)

    def test_usa_o_patamar_de_backoff_da_tentativa_pos_incremento(self):
        # Achado de revisão adversarial (1a rodada): um teste anterior aqui
        # só verificava "delta > 60s", o que passaria mesmo se o código
        # (erradamente) passasse pedido.tentativas (valor ANTES do
        # incremento) para calcular_backoff_segundos em vez de
        # tentativas_novas (valor DEPOIS) -- com jitter, o patamar de 60s
        # errado ainda podia superar 60s exatos. Este teste usa um rng SEM
        # jitter (uniform sempre 0.0) e compara contra o patamar EXATO
        # esperado para tentativas_novas=2 (índice 1 de BACKOFF_BASE_SEGUNDOS,
        # 300s) -- se o código usasse o valor errado (tentativa=1, 60s),
        # esta asserção falharia.
        pedido = _pedido_em_andamento(tentativas=1)
        agora = T0 + timedelta(minutes=10)
        resultado = varrer_lease_vencida(
            pedido, agora=agora, max_tentativas=5, rng=_SemJitter()
        )
        delta_segundos = (resultado.pedido.proximo_tentativa_em - agora).total_seconds()
        esperado = BACKOFF_BASE_SEGUNDOS[1]  # tentativas_novas=2 -> índice 1 (300s)
        self.assertAlmostEqual(delta_segundos, esperado, places=6)

    def test_diagnostico_registrado_em_precisa_ser_tz_aware(self):
        with self.assertRaises(ValueError):
            DiagnosticoPedido(
                request_id="req-1",
                motivo="teste",
                status_anterior=RequestStatus.EM_ANDAMENTO,
                tentativas=1,
                registrado_em=datetime(2026, 1, 1),
            )


class TestPromoverRetentativaPronta(unittest.TestCase):
    def _pedido_retentativa(self, proximo_tentativa_em):
        pedido = _pedido_em_andamento()
        resultado = varrer_lease_vencida(
            pedido, agora=T0 + timedelta(minutes=10), rng=random.Random(1)
        )
        return _com_campos(resultado.pedido, proximo_tentativa_em=proximo_tentativa_em)

    def test_promove_quando_hora_ja_chegou(self):
        pronto_em = T0 + timedelta(minutes=15)
        pedido = self._pedido_retentativa(pronto_em)
        promovido = promover_retentativa_pronta(pedido, agora=pronto_em)
        self.assertEqual(promovido.status, RequestStatus.PENDENTE)
        self.assertIsNone(promovido.proximo_tentativa_em)
        # tentativas preservada -- o contador continua valendo para a
        # próxima rodada de assumir_pedido/varrer_lease_vencida.
        self.assertEqual(promovido.tentativas, pedido.tentativas)

    def test_nao_promove_antes_da_hora(self):
        pronto_em = T0 + timedelta(minutes=15)
        pedido = self._pedido_retentativa(pronto_em)
        with self.assertRaises(ValueError):
            promover_retentativa_pronta(pedido, agora=pronto_em - timedelta(seconds=1))

    def test_status_diferente_de_retentativa_agendada_rejeitado(self):
        with self.assertRaises(ValueError):
            promover_retentativa_pronta(_pedido_pendente(), agora=T0)

    def test_sem_proximo_tentativa_em_rejeitado(self):
        pedido = PedidoDuravel(request_id="req-1", status=RequestStatus.RETENTATIVA_AGENDADA)
        with self.assertRaises(ValueError):
            promover_retentativa_pronta(pedido, agora=T0)


class TestReassumirAposSweepLimpaProximaTentativa(unittest.TestCase):
    def test_assumir_pedido_limpa_proximo_tentativa_em(self):
        pedido = _pedido_em_andamento()
        resultado = varrer_lease_vencida(
            pedido, agora=T0 + timedelta(minutes=10), rng=random.Random(1)
        )
        pronto = promover_retentativa_pronta(
            resultado.pedido, agora=resultado.pedido.proximo_tentativa_em
        )
        reassumido = assumir_pedido(
            pronto, "executor-b", "run-2", agora=resultado.pedido.proximo_tentativa_em
        )
        self.assertIsNone(reassumido.proximo_tentativa_em)
        self.assertEqual(reassumido.tentativas, 1)


if __name__ == "__main__":
    unittest.main()
