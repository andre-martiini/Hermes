"""Testes de `autonomy/execution.py` -- só lógica pura, sem I/O (P04
sub-entrega 3/N: "Implementar assumir, renovar, registrar progresso e
registrar resultado observado" do plano de autonomia).

Cobre a orquestração de `PedidoDuravel` (assumir/renovar/progresso/
resultado), fencing propagado de `autonomy.requests` e idempotência/conflito
propagados de `autonomy.ledger`.
"""

import unittest
from datetime import datetime, timedelta, timezone

from autonomy.ledger import ConflitoIdempotencia
from autonomy.requests import ESTADOS_TERMINAIS, RequestStatus
from autonomy.execution import (
    LeaseInvalida,
    PedidoDuravel,
    assumir_pedido,
    pedido_esta_ativo,
    registrar_progresso,
    registrar_resultado_observado,
    renovar_pedido,
)

T0 = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)


def _pedido_pendente(request_id: str = "req-1") -> PedidoDuravel:
    return PedidoDuravel(request_id=request_id, status=RequestStatus.PENDENTE)


class TestPedidoDuravel(unittest.TestCase):
    def test_request_id_vazio_rejeitado(self):
        with self.assertRaises(ValueError):
            PedidoDuravel(request_id="   ", status=RequestStatus.PENDENTE)

    def test_request_id_e_normalizado(self):
        pedido = PedidoDuravel(request_id="  req-1  ", status=RequestStatus.PENDENTE)
        self.assertEqual(pedido.request_id, "req-1")

    def test_estado_inicial_sem_lease_nem_ledger(self):
        pedido = _pedido_pendente()
        self.assertIsNone(pedido.lease)
        self.assertIsNone(pedido.ledger_entry)


class TestAssumirPedido(unittest.TestCase):
    def test_assume_pedido_pendente(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", agora=T0)
        self.assertEqual(pedido.status, RequestStatus.RESERVADO)
        self.assertIsNotNone(pedido.lease)
        self.assertEqual(pedido.lease.generation, 1)
        self.assertEqual(pedido.lease.executor_id, "executor-a")

    def test_assumir_pedido_ja_reservado_falha(self):
        # RESERVADO -> RESERVADO não é uma transição válida (não é
        # reentrega idempotente do MESMO executor: duas reservas deveriam
        # sempre passar por outra rota que não esta).
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", agora=T0)
        with self.assertRaises(ValueError):
            assumir_pedido(pedido, "executor-b", agora=T0)

    def test_assumir_pedido_concluido_falha(self):
        pedido = PedidoDuravel(request_id="req-1", status=RequestStatus.CONCLUIDO)
        with self.assertRaises(ValueError):
            assumir_pedido(pedido, "executor-a", agora=T0)

    def test_reassumir_apos_retentativa_incrementa_geracao(self):
        primeiro = assumir_pedido(_pedido_pendente(), "executor-a", agora=T0)
        de_novo = PedidoDuravel(
            request_id=primeiro.request_id,
            status=RequestStatus.RETENTATIVA_AGENDADA,
            lease=primeiro.lease,
            ledger_entry=primeiro.ledger_entry,
        )
        reassumido = assumir_pedido(de_novo, "executor-c", agora=T0 + timedelta(minutes=10))
        self.assertEqual(reassumido.status, RequestStatus.RESERVADO)
        self.assertEqual(reassumido.lease.generation, 2)
        self.assertEqual(reassumido.lease.executor_id, "executor-c")
        # Token antigo não serve mais para nada (fencing por geração).
        self.assertNotEqual(reassumido.lease.lease_token, primeiro.lease.lease_token)


class TestRenovarPedido(unittest.TestCase):
    def test_renova_mantendo_token_e_geracao(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", agora=T0)
        renovado = renovar_pedido(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            agora=T0 + timedelta(minutes=1),
        )
        self.assertEqual(renovado.lease.lease_token, pedido.lease.lease_token)
        self.assertEqual(renovado.lease.generation, pedido.lease.generation)
        self.assertGreater(renovado.lease.expires_at, pedido.lease.expires_at)
        # Renovar não é uma transição de status.
        self.assertEqual(renovado.status, RequestStatus.RESERVADO)

    def test_renovar_sem_lease_nenhuma_falha(self):
        with self.assertRaises(LeaseInvalida):
            renovar_pedido(_pedido_pendente(), "token-qualquer", 1, agora=T0)

    def test_renovar_com_token_errado_falha(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", agora=T0)
        with self.assertRaises(LeaseInvalida):
            renovar_pedido(pedido, "token-errado", pedido.lease.generation, agora=T0)

    def test_renovar_com_geracao_velha_falha_apos_reassumir(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", agora=T0)
        # Lease expira e o pedido é reassumido por outro executor.
        expirado = PedidoDuravel(
            request_id=pedido.request_id,
            status=RequestStatus.RETENTATIVA_AGENDADA,
            lease=pedido.lease,
        )
        reassumido = assumir_pedido(expirado, "executor-b", agora=T0 + timedelta(minutes=10))
        # O executor original tenta renovar com o token/geração antigos.
        with self.assertRaises(LeaseInvalida):
            renovar_pedido(
                reassumido, pedido.lease.lease_token, pedido.lease.generation,
                agora=T0 + timedelta(minutes=11),
            )

    def test_renovar_com_lease_expirada_falha(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", agora=T0, duracao_segundos=60)
        with self.assertRaises(LeaseInvalida):
            renovar_pedido(
                pedido, pedido.lease.lease_token, pedido.lease.generation,
                agora=T0 + timedelta(minutes=5),
            )


class TestRegistrarProgresso(unittest.TestCase):
    def test_abre_ledger_e_avanca_para_em_andamento(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", agora=T0)
        atualizado = registrar_progresso(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 1}, agora=T0,
        )
        self.assertEqual(atualizado.status, RequestStatus.EM_ANDAMENTO)
        self.assertIsNotNone(atualizado.ledger_entry)
        self.assertEqual(len(atualizado.ledger_entry.checkpoints), 1)
        self.assertEqual(atualizado.ledger_entry.checkpoints[0].dados, {"passo": 1})

    def test_segunda_chamada_reusa_entrada_e_acrescenta_checkpoint(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", agora=T0)
        pedido = registrar_progresso(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 1}, agora=T0,
        )
        pedido = registrar_progresso(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 2}, agora=T0 + timedelta(seconds=30),
        )
        self.assertEqual(pedido.status, RequestStatus.EM_ANDAMENTO)
        self.assertEqual(len(pedido.ledger_entry.checkpoints), 2)
        self.assertEqual(pedido.ledger_entry.checkpoints[-1].dados, {"passo": 2})

    def test_reentrega_do_mesmo_checkpoint_e_no_op_de_sequencia(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", agora=T0)
        pedido = registrar_progresso(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 1}, agora=T0,
        )
        de_novo = registrar_progresso(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 1}, agora=T0 + timedelta(seconds=5),
        )
        self.assertEqual(len(de_novo.ledger_entry.checkpoints), 1)

    def test_payload_diferente_mesma_chave_levanta_conflito(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", agora=T0)
        pedido = registrar_progresso(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 1}, agora=T0,
        )
        with self.assertRaises(ConflitoIdempotencia):
            registrar_progresso(
                pedido, pedido.lease.lease_token, pedido.lease.generation,
                "op-1", {"acao": "y"}, {"passo": 2}, agora=T0,
            )

    def test_fencing_invalido_impede_progresso(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", agora=T0)
        with self.assertRaises(LeaseInvalida):
            registrar_progresso(
                pedido, "token-errado", pedido.lease.generation,
                "op-1", {"acao": "x"}, {"passo": 1}, agora=T0,
            )
        # Nenhuma mutação deve ter acontecido -- pedido original intacto.
        self.assertIsNone(pedido.ledger_entry)

    def test_progresso_em_pedido_ainda_pendente_falha(self):
        # Sem lease nenhuma (pedido nunca foi assumido) -- fencing reprova
        # antes mesmo de checar a transição de status.
        with self.assertRaises(LeaseInvalida):
            registrar_progresso(
                _pedido_pendente(), "qualquer", 1,
                "op-1", {"acao": "x"}, {"passo": 1}, agora=T0,
            )


class TestRegistrarResultadoObservado(unittest.TestCase):
    def _pedido_em_andamento(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", agora=T0)
        return registrar_progresso(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 1}, agora=T0,
        )

    def test_conclui_com_resultado(self):
        pedido = self._pedido_em_andamento()
        concluido = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(minutes=1),
        )
        self.assertEqual(concluido.status, RequestStatus.CONCLUIDO)
        self.assertEqual(concluido.ledger_entry.resultado, {"ok": True})
        self.assertFalse(pedido_esta_ativo(concluido))

    def test_falha_final_tambem_e_aceita(self):
        pedido = self._pedido_em_andamento()
        falhou = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"erro": "permanente"}, RequestStatus.FALHA_FINAL, agora=T0,
        )
        self.assertEqual(falhou.status, RequestStatus.FALHA_FINAL)
        self.assertFalse(pedido_esta_ativo(falhou))

    def test_transicao_nao_permitida_e_rejeitada(self):
        # EM_ANDAMENTO não pode pular direto para PENDENTE.
        pedido = self._pedido_em_andamento()
        with self.assertRaises(ValueError):
            registrar_resultado_observado(
                pedido, pedido.lease.lease_token, pedido.lease.generation,
                {"ok": True}, RequestStatus.PENDENTE, agora=T0,
            )

    def test_sem_ledger_aberto_falha(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", agora=T0)
        with self.assertRaises(ValueError):
            registrar_resultado_observado(
                pedido, pedido.lease.lease_token, pedido.lease.generation,
                {"ok": True}, RequestStatus.CONCLUIDO, agora=T0,
            )

    def test_reentrega_do_mesmo_resultado_e_idempotente(self):
        pedido = self._pedido_em_andamento()
        concluido = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0,
        )
        de_novo = registrar_resultado_observado(
            concluido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(seconds=1),
        )
        self.assertEqual(de_novo.status, RequestStatus.CONCLUIDO)
        self.assertEqual(de_novo.ledger_entry.resultado, {"ok": True})

    def test_resultado_diferente_apos_concluido_levanta_valueerror(self):
        pedido = self._pedido_em_andamento()
        concluido = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0,
        )
        with self.assertRaises(ValueError):
            registrar_resultado_observado(
                concluido, pedido.lease.lease_token, pedido.lease.generation,
                {"ok": False}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(seconds=1),
            )

    def test_fencing_invalido_impede_resultado(self):
        pedido = self._pedido_em_andamento()
        with self.assertRaises(LeaseInvalida):
            registrar_resultado_observado(
                pedido, "token-errado", pedido.lease.generation,
                {"ok": True}, RequestStatus.CONCLUIDO, agora=T0,
            )
        self.assertIsNone(pedido.ledger_entry.resultado_registrado_em)


class TestPedidoEstaAtivo(unittest.TestCase):
    def test_estados_terminais_nao_estao_ativos(self):
        for terminal in ESTADOS_TERMINAIS:
            with self.subTest(terminal=terminal):
                pedido = PedidoDuravel(request_id="req-1", status=terminal)
                self.assertFalse(pedido_esta_ativo(pedido))

    def test_estados_nao_terminais_estao_ativos(self):
        for status in RequestStatus:
            if status in ESTADOS_TERMINAIS:
                continue
            with self.subTest(status=status):
                pedido = PedidoDuravel(request_id="req-1", status=status)
                self.assertTrue(pedido_esta_ativo(pedido))


if __name__ == "__main__":
    unittest.main()
