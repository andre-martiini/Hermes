"""Testes de `autonomy/execution.py` -- só lógica pura, sem I/O (P04
sub-entrega 3/N: "Implementar assumir, renovar, registrar progresso e
registrar resultado observado" do plano de autonomia; sub-entrega 5/N
acrescenta a costura de `AgentRun`, ver `TestPedidoRunWiring` abaixo).

Cobre a orquestração de `PedidoDuravel` (assumir/renovar/progresso/
resultado), fencing propagado de `autonomy.requests`, idempotência/conflito
propagados de `autonomy.ledger` e o ciclo de `AgentRun` (`autonomy.runs`)
costurado em `pedido.run`.
"""

import dataclasses
import unittest
from datetime import datetime, timedelta, timezone

from autonomy.ledger import ConflitoIdempotencia
from autonomy.requests import ESTADOS_TERMINAIS, RequestStatus
from autonomy.runs import AgentRunStatus, RunLeaseInvalida
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
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-6", agora=T0)
        self.assertEqual(pedido.status, RequestStatus.RESERVADO)
        self.assertIsNotNone(pedido.lease)
        self.assertEqual(pedido.lease.generation, 1)
        self.assertEqual(pedido.lease.executor_id, "executor-a")

    def test_assumir_pedido_ja_reservado_falha(self):
        # RESERVADO -> RESERVADO não é uma transição válida (não é
        # reentrega idempotente do MESMO executor: duas reservas deveriam
        # sempre passar por outra rota que não esta).
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-7", agora=T0)
        with self.assertRaises(ValueError):
            assumir_pedido(pedido, "executor-b", "run-1", agora=T0)

    def test_assumir_pedido_concluido_falha(self):
        pedido = PedidoDuravel(request_id="req-1", status=RequestStatus.CONCLUIDO)
        with self.assertRaises(ValueError):
            assumir_pedido(pedido, "executor-a", "run-2", agora=T0)

    def test_reassumir_apos_retentativa_incrementa_geracao(self):
        primeiro = assumir_pedido(_pedido_pendente(), "executor-a", "run-10", agora=T0)
        de_novo = PedidoDuravel(
            request_id=primeiro.request_id,
            status=RequestStatus.RETENTATIVA_AGENDADA,
            lease=primeiro.lease,
            ledger_entry=primeiro.ledger_entry,
        )
        reassumido = assumir_pedido(de_novo, "executor-c", "run-3", agora=T0 + timedelta(minutes=10))
        self.assertEqual(reassumido.status, RequestStatus.RESERVADO)
        self.assertEqual(reassumido.lease.generation, 2)
        self.assertEqual(reassumido.lease.executor_id, "executor-c")
        # Token antigo não serve mais para nada (fencing por geração).
        self.assertNotEqual(reassumido.lease.lease_token, primeiro.lease.lease_token)

    def test_assumir_com_lease_anterior_ainda_valida_falha(self):
        # Achado de revisão adversarial: reassumir não pode "roubar" uma
        # lease que ainda não expirou, mesmo que o status permita a
        # transição para RESERVADO (ex.: RETENTATIVA_AGENDADA).
        primeiro = assumir_pedido(_pedido_pendente(), "executor-a", "run-12", agora=T0)
        de_novo = PedidoDuravel(
            request_id=primeiro.request_id,
            status=RequestStatus.RETENTATIVA_AGENDADA,
            lease=primeiro.lease,
        )
        with self.assertRaises(LeaseInvalida):
            # Lease de 5 minutos emitida em T0; ainda válida 1 minuto depois.
            assumir_pedido(de_novo, "executor-b", "run-4", agora=T0 + timedelta(minutes=1))


class TestRenovarPedido(unittest.TestCase):
    def test_renova_mantendo_token_e_geracao(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-14", agora=T0)
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
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-15", agora=T0)
        with self.assertRaises(LeaseInvalida):
            renovar_pedido(pedido, "token-errado", pedido.lease.generation, agora=T0)

    def test_renovar_com_geracao_velha_falha_apos_reassumir(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-16", agora=T0)
        # Lease expira e o pedido é reassumido por outro executor.
        expirado = PedidoDuravel(
            request_id=pedido.request_id,
            status=RequestStatus.RETENTATIVA_AGENDADA,
            lease=pedido.lease,
        )
        reassumido = assumir_pedido(expirado, "executor-b", "run-5", agora=T0 + timedelta(minutes=10))
        # O executor original tenta renovar com o token/geração antigos.
        with self.assertRaises(LeaseInvalida):
            renovar_pedido(
                reassumido, pedido.lease.lease_token, pedido.lease.generation,
                agora=T0 + timedelta(minutes=11),
            )

    def test_renovar_com_lease_expirada_falha(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-18", agora=T0, duracao_segundos=60)
        with self.assertRaises(LeaseInvalida):
            renovar_pedido(
                pedido, pedido.lease.lease_token, pedido.lease.generation,
                agora=T0 + timedelta(minutes=5),
            )

    def test_renovar_em_retentativa_agendada_falha_mesmo_com_lease_ainda_valida(self):
        # Achado de revisão adversarial (Codex, PR #330, P1): sem excluir
        # RETENTATIVA_AGENDADA (além de ESTADOS_TERMINAIS), um executor
        # "zumbi" podia renovar indefinidamente a lease de um pedido
        # agendado para retentativa, impedindo QUALQUER outro executor de
        # jamais reivindicá-lo (assumir_pedido corretamente recusa
        # reassumir enquanto a lease anterior não expira).
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-19", agora=T0)
        agendado_para_retentativa = PedidoDuravel(
            request_id=pedido.request_id,
            status=RequestStatus.RETENTATIVA_AGENDADA,
            lease=pedido.lease,
        )
        with self.assertRaises(ValueError):
            renovar_pedido(
                agendado_para_retentativa, pedido.lease.lease_token, pedido.lease.generation,
                agora=T0 + timedelta(minutes=1),
            )

    def test_renovar_em_resultado_desconhecido_falha(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-20", agora=T0)
        aguardando_reconciliacao = PedidoDuravel(
            request_id=pedido.request_id,
            status=RequestStatus.RESULTADO_DESCONHECIDO,
            lease=pedido.lease,
        )
        with self.assertRaises(ValueError):
            renovar_pedido(
                aguardando_reconciliacao, pedido.lease.lease_token, pedido.lease.generation,
                agora=T0 + timedelta(minutes=1),
            )

    def test_renovar_pedido_terminal_falha_mesmo_com_lease_ainda_valida(self):
        # Achado de revisão adversarial: nenhuma função limpa `lease` ao
        # concluir um pedido -- sem checar `pedido_esta_ativo`, a lease
        # emitida antes da conclusão continuava "renovável" até seu
        # próprio expires_at original, mesmo com o pedido já CONCLUIDO.
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-21", agora=T0)
        pedido = registrar_progresso(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 1}, agora=T0,
        )
        concluido = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(seconds=5),
        )
        with self.assertRaises(ValueError):
            renovar_pedido(
                concluido, concluido.lease.lease_token, concluido.lease.generation,
                agora=T0 + timedelta(seconds=10),
            )


class TestRegistrarProgresso(unittest.TestCase):
    def test_abre_ledger_e_avanca_para_em_andamento(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-22", agora=T0)
        atualizado = registrar_progresso(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 1}, agora=T0,
        )
        self.assertEqual(atualizado.status, RequestStatus.EM_ANDAMENTO)
        self.assertIsNotNone(atualizado.ledger_entry)
        self.assertEqual(len(atualizado.ledger_entry.checkpoints), 1)
        self.assertEqual(atualizado.ledger_entry.checkpoints[0].dados, {"passo": 1})

    def test_segunda_chamada_reusa_entrada_e_acrescenta_checkpoint(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-23", agora=T0)
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
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-24", agora=T0)
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
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-25", agora=T0)
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
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-26", agora=T0)
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
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-27", agora=T0)
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
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-28", agora=T0)
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

    def test_reentrega_do_mesmo_resultado_e_idempotente_mesmo_com_lease_expirada(self):
        # Achado de revisão adversarial (Codex, PR #330, P2): se a resposta
        # da 1a chamada se perdeu, o consumidor retenta com o MESMO
        # token/geração depois que a lease (5 minutos por padrão) já
        # venceu -- essa reentrega precisa continuar valendo, porque o
        # resultado já está definitivamente registrado (item 9: reentrega
        # retorna o resultado já observado, não depende de lease viva).
        pedido = self._pedido_em_andamento()
        concluido = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(seconds=5),
        )
        de_novo = registrar_resultado_observado(
            concluido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(minutes=10),
        )
        self.assertEqual(de_novo.status, RequestStatus.CONCLUIDO)
        self.assertEqual(de_novo.ledger_entry.resultado, {"ok": True})

    def test_reentrega_apos_lease_expirada_ainda_exige_token_correto(self):
        # O bypass de lease vencida (P2 acima) não abre mão de autenticar
        # quem está lendo -- token/geração errados continuam rejeitados
        # mesmo para um pedido já concluído.
        pedido = self._pedido_em_andamento()
        concluido = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(seconds=5),
        )
        with self.assertRaises(LeaseInvalida):
            registrar_resultado_observado(
                concluido, "token-errado", pedido.lease.generation,
                {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(minutes=10),
            )

    def test_reentrega_apos_lease_expirada_com_resultado_diferente_ainda_falha(self):
        # O bypass não enfraquece a garantia de nunca sobrescrever: mesmo
        # com a lease vencida, um resultado DIFERENTE do já registrado
        # continua levantando ValueError (autonomy.ledger.registrar_resultado
        # é o árbitro final de "idêntico").
        pedido = self._pedido_em_andamento()
        concluido = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(seconds=5),
        )
        with self.assertRaises(ValueError):
            registrar_resultado_observado(
                concluido, pedido.lease.lease_token, pedido.lease.generation,
                {"ok": False}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(minutes=10),
            )

    def test_status_nao_terminal_e_rejeitado_sem_selar_o_ledger(self):
        # Achado de revisão adversarial (o mais grave desta sub-entrega):
        # aceitar RETENTATIVA_AGENDADA aqui selava o ledger permanentemente
        # (autonomy.ledger.registrar_resultado nunca sobrescreve), mas o
        # pedido continuava "ativo" e precisaria chamar registrar_progresso
        # de novo na mesma operação para a retentativa -- o que nunca mais
        # seria possível (ledger selado recusa checkpoint novo). Reproduz o
        # cenário exato do achado: RETENTATIVA_AGENDADA precisa ser
        # rejeitado ANTES de tocar o ledger, e um reassumir+retomar
        # subsequente precisa continuar funcionando.
        for status_nao_terminal in (
            RequestStatus.RETENTATIVA_AGENDADA,
            RequestStatus.RESULTADO_DESCONHECIDO,
            RequestStatus.AGUARDANDO_APROVACAO,
            RequestStatus.AGUARDANDO_EXTERNO,
        ):
            with self.subTest(status_nao_terminal=status_nao_terminal):
                pedido = self._pedido_em_andamento()
                with self.assertRaises(ValueError):
                    registrar_resultado_observado(
                        pedido, pedido.lease.lease_token, pedido.lease.generation,
                        {"motivo": "timeout"}, status_nao_terminal, agora=T0,
                    )
                # Ledger não foi tocado -- continua aberto e utilizável.
                self.assertIsNone(pedido.ledger_entry.resultado_registrado_em)

    def test_apos_rejeicao_de_status_nao_terminal_retentativa_ainda_funciona(self):
        # Confirma de ponta a ponta que o fix não deixou o pedido preso: a
        # tentativa de selar com RETENTATIVA_AGENDADA falha SEM tocar o
        # ledger, então o fluxo real de retentativa (fora do escopo desta
        # fatia -- nenhuma função daqui produz RETENTATIVA_AGENDADA ainda,
        # ver docstring de registrar_resultado_observado) continua possível
        # depois que outro mecanismo decidir agendar a retentativa: reassumir
        # após a lease expirar e continuar registrando progresso na MESMA
        # operação (mesmo idempotency_key, ledger_entry preservado).
        pedido = self._pedido_em_andamento()
        with self.assertRaises(ValueError):
            registrar_resultado_observado(
                pedido, pedido.lease.lease_token, pedido.lease.generation,
                {"motivo": "timeout"}, RequestStatus.RETENTATIVA_AGENDADA, agora=T0,
            )
        agendado_para_retentativa = PedidoDuravel(
            request_id=pedido.request_id,
            status=RequestStatus.RETENTATIVA_AGENDADA,
            lease=pedido.lease,
            ledger_entry=pedido.ledger_entry,
        )
        reassumido = assumir_pedido(
            agendado_para_retentativa, "executor-b", "run-6", agora=T0 + timedelta(minutes=10)
        )
        retomado = registrar_progresso(
            reassumido, reassumido.lease.lease_token, reassumido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 2}, agora=T0 + timedelta(minutes=10),
        )
        self.assertEqual(len(retomado.ledger_entry.checkpoints), 2)
        concluido = registrar_resultado_observado(
            retomado, retomado.lease.lease_token, retomado.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(minutes=11),
        )
        self.assertEqual(concluido.status, RequestStatus.CONCLUIDO)


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


class TestPedidoRunWiring(unittest.TestCase):
    """P04 sub-entrega 5/N: costura de `autonomy.runs.AgentRun` dentro de
    `PedidoDuravel`. `autonomy/runs.py` (sub-entrega 4/N) e `autonomy/
    execution.py` (sub-entrega 3/N) nunca se conheciam antes desta fatia --
    ver docstrings de `PedidoDuravel`/`assumir_pedido`/`registrar_progresso`/
    `registrar_resultado_observado` para a justificativa completa de cada
    decisão coberta aqui."""

    def _pedido_em_andamento(self, run_id: str = "run-wiring-1"):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", run_id, agora=T0)
        return registrar_progresso(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 1}, agora=T0,
        )

    def test_assumir_pedido_cria_run_iniciado(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-1", agora=T0)
        self.assertIsNotNone(pedido.run)
        self.assertEqual(pedido.run.run_id, "run-1")
        self.assertEqual(pedido.run.request_id, "req-1")
        self.assertEqual(pedido.run.executor_id, "executor-a")
        self.assertEqual(pedido.run.status, AgentRunStatus.INICIADO)
        self.assertEqual(pedido.run.iniciado_em, T0)

    def test_run_nasce_com_o_mesmo_token_e_geracao_da_lease(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-1", agora=T0)
        self.assertEqual(pedido.run.lease_token, pedido.lease.lease_token)
        self.assertEqual(pedido.run.generation, pedido.lease.generation)

    def test_reassumir_cria_run_novo_com_geracao_nova(self):
        primeiro = assumir_pedido(_pedido_pendente(), "executor-a", "run-1", agora=T0)
        de_novo = PedidoDuravel(
            request_id=primeiro.request_id,
            status=RequestStatus.RETENTATIVA_AGENDADA,
            lease=primeiro.lease,
            run=primeiro.run,
        )
        reassumido = assumir_pedido(
            de_novo, "executor-c", "run-2", agora=T0 + timedelta(minutes=10)
        )
        # Novo run, não o mesmo objeto reaproveitado -- mesmo espírito de
        # "múltiplas tentativas produzem múltiplos AgentRun" (docstring de
        # autonomy.runs).
        self.assertEqual(reassumido.run.run_id, "run-2")
        self.assertEqual(reassumido.run.generation, 2)
        self.assertEqual(reassumido.run.executor_id, "executor-c")
        self.assertEqual(reassumido.run.status, AgentRunStatus.INICIADO)
        # O run da tentativa anterior não é mutado por esta chamada -- ele
        # continua acessível a partir do objeto antigo (imutabilidade).
        self.assertEqual(primeiro.run.generation, 1)
        self.assertEqual(primeiro.run.status, AgentRunStatus.INICIADO)

    def test_registrar_progresso_marca_run_em_andamento(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-1", agora=T0)
        atualizado = registrar_progresso(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 1}, agora=T0,
        )
        self.assertEqual(atualizado.run.status, AgentRunStatus.EM_ANDAMENTO)
        self.assertEqual(atualizado.run.run_id, "run-1")

    def test_registrar_progresso_repetido_nao_toca_o_run_de_novo(self):
        # Corrigido apos achado do Codex (PR #339): marcar_em_andamento roda
        # em TODA chamada com pedido.run presente (nao so na "primeira",
        # ver docstring de registrar_progresso), mas continua um no-op
        # idempotente (mesma identidade de objeto devolvida, sem mudanca)
        # quando o run ja esta EM_ANDAMENTO -- e o que este teste verifica.
        pedido = self._pedido_em_andamento()
        de_novo = registrar_progresso(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 2}, agora=T0 + timedelta(seconds=5),
        )
        self.assertIs(de_novo.run, pedido.run)
        self.assertEqual(de_novo.run.status, AgentRunStatus.EM_ANDAMENTO)

    def test_registrar_progresso_repara_run_iniciado_quando_pedido_ja_em_andamento(self):
        # Achado real de revisao adversarial (Codex, PR #339): um wiring
        # futuro com escrita nao-atomica de pedido/run pode deixar o PEDIDO
        # ja EM_ANDAMENTO enquanto o run correspondente ainda esta INICIADO
        # (a escrita do pedido terminou, a do run nao, entre uma queda e uma
        # retentativa). Simula essa inconsistencia diretamente e confirma
        # que uma chamada seguinte de registrar_progresso REPARA o run para
        # EM_ANDAMENTO, em vez de deixa-lo INICIADO para sempre (o defeito
        # que A02/autonomy.runs existem para evitar).
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-1", agora=T0)
        run_ainda_iniciado = pedido.run
        pedido_inconsistente = dataclasses.replace(
            pedido, status=RequestStatus.EM_ANDAMENTO, run=run_ainda_iniciado
        )
        reparado = registrar_progresso(
            pedido_inconsistente, pedido.lease.lease_token, pedido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 1}, agora=T0 + timedelta(seconds=1),
        )
        self.assertEqual(reparado.run.status, AgentRunStatus.EM_ANDAMENTO)

    def test_registrar_progresso_sem_run_nao_quebra(self):
        # Pedido construído diretamente, sem passar por assumir_pedido --
        # tolerado (ver docstring de PedidoDuravel), só a peça de
        # ledger/status continua funcionando.
        pedido = PedidoDuravel(
            request_id="req-legado",
            status=RequestStatus.RESERVADO,
            lease=assumir_pedido(_pedido_pendente(), "executor-a", "run-1", agora=T0).lease,
        )
        atualizado = registrar_progresso(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            "op-1", {"acao": "x"}, {"passo": 1}, agora=T0,
        )
        self.assertIsNone(atualizado.run)
        self.assertEqual(atualizado.status, RequestStatus.EM_ANDAMENTO)

    def test_conclusao_fecha_run_como_concluido_com_resultado(self):
        pedido = self._pedido_em_andamento()
        concluido = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(minutes=1),
        )
        self.assertEqual(concluido.run.status, AgentRunStatus.CONCLUIDO)
        self.assertEqual(concluido.run.resultado, {"ok": True})
        self.assertEqual(concluido.run.finalizado_em, T0 + timedelta(minutes=1))

    def test_falha_final_fecha_run_como_falha(self):
        pedido = self._pedido_em_andamento()
        falhou = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"erro": "permanente"}, RequestStatus.FALHA_FINAL, agora=T0,
        )
        self.assertEqual(falhou.run.status, AgentRunStatus.FALHA)
        self.assertEqual(falhou.run.resultado, {"erro": "permanente"})

    def test_cancelado_fecha_run_como_falha(self):
        # Decisão desta sub-entrega (ver _REQUEST_STATUS_PARA_AGENT_RUN_STATUS
        # em autonomy/execution.py): AgentRun não tem desfecho próprio de
        # cancelamento -- CANCELADO do pedido mapeia para FALHA no run,
        # porque a tentativa em curso não produziu um resultado bem-sucedido.
        pedido = self._pedido_em_andamento()
        cancelado = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"motivo": "cancelado pelo usuário"}, RequestStatus.CANCELADO, agora=T0,
        )
        self.assertEqual(cancelado.status, RequestStatus.CANCELADO)
        self.assertEqual(cancelado.run.status, AgentRunStatus.FALHA)

    def test_resultado_observado_sem_run_nao_quebra(self):
        # Simula um pedido legado/pré-wiring que chegou aqui sem nenhum
        # AgentRun associado (ver docstring de PedidoDuravel).
        pedido = self._pedido_em_andamento()
        sem_run = dataclasses.replace(pedido, run=None)
        concluido = registrar_resultado_observado(
            sem_run, sem_run.lease.lease_token, sem_run.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0,
        )
        self.assertIsNone(concluido.run)
        self.assertEqual(concluido.status, RequestStatus.CONCLUIDO)

    def test_reentrega_do_mesmo_resultado_e_idempotente_no_run(self):
        pedido = self._pedido_em_andamento()
        concluido = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(seconds=5),
        )
        de_novo = registrar_resultado_observado(
            concluido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(minutes=10),
        )
        self.assertEqual(de_novo.run.status, AgentRunStatus.CONCLUIDO)
        self.assertEqual(de_novo.run.resultado, {"ok": True})
        # Reentrega não regrava finalizado_em -- concluir_run devolve o
        # MESMO run (não uma cópia com timestamp novo) no caminho idempotente.
        self.assertEqual(de_novo.run.finalizado_em, T0 + timedelta(seconds=5))

    def test_reentrega_com_resultado_diferente_nao_toca_run(self):
        # O ledger levanta ValueError ANTES de qualquer tentativa de fechar
        # o run -- run permanece no estado terminal original, não muda para
        # um resultado diferente nem levanta um erro próprio (RunFinalizado)
        # que mascararia a causa raiz (ledger).
        pedido = self._pedido_em_andamento()
        concluido = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(seconds=5),
        )
        with self.assertRaises(ValueError):
            registrar_resultado_observado(
                concluido, pedido.lease.lease_token, pedido.lease.generation,
                {"ok": False}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(minutes=10),
            )
        self.assertEqual(concluido.run.resultado, {"ok": True})

    def test_fencing_invalido_no_progresso_nao_toca_run(self):
        pedido = assumir_pedido(_pedido_pendente(), "executor-a", "run-1", agora=T0)
        with self.assertRaises(LeaseInvalida):
            registrar_progresso(
                pedido, "token-errado", pedido.lease.generation,
                "op-1", {"acao": "x"}, {"passo": 1}, agora=T0,
            )
        self.assertEqual(pedido.run.status, AgentRunStatus.INICIADO)

    def test_fencing_invalido_no_resultado_nao_toca_run(self):
        pedido = self._pedido_em_andamento()
        with self.assertRaises(LeaseInvalida):
            registrar_resultado_observado(
                pedido, "token-errado", pedido.lease.generation,
                {"ok": True}, RequestStatus.CONCLUIDO, agora=T0,
            )
        self.assertEqual(pedido.run.status, AgentRunStatus.EM_ANDAMENTO)

    def test_reentrega_com_run_ainda_ativo_e_lease_vencida_nao_fecha_o_run_as_escuras(self):
        # Achado de revisão adversarial: uma versão anterior de
        # _fechar_run_se_houver passava lease_ainda_valida=True fixo no
        # caminho de reentrega, sob a alegação de que concluir_run "ignora
        # esse parâmetro de qualquer forma (run já terminal)" -- mas isso só
        # vale quando pedido.run JÁ está terminal, o que nunca era
        # conferido. Simula a inconsistência que um wiring futuro com
        # escrita não-atômica de pedido/run poderia produzir (pedido/ledger
        # já selados, mas o run correspondente nunca foi fechado): reentrega
        # do MESMO resultado, bem depois da lease original expirar, precisa
        # levantar RunLeaseInvalida em vez de forçar o run a CONCLUIDO sem
        # nenhuma lease real ainda válida por trás.
        pedido = self._pedido_em_andamento()
        run_ainda_ativo = pedido.run
        concluido = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(seconds=5),
        )
        inconsistente = dataclasses.replace(concluido, run=run_ainda_ativo)
        with self.assertRaises(RunLeaseInvalida):
            registrar_resultado_observado(
                inconsistente, pedido.lease.lease_token, pedido.lease.generation,
                {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(minutes=10),
            )
        # O ledger (já selado antes) segue intacto -- só a tentativa de
        # fechar o run é que é rejeitada.
        self.assertEqual(inconsistente.ledger_entry.resultado, {"ok": True})

    def test_reentrega_com_run_ainda_ativo_e_lease_valida_fecha_o_run(self):
        # Contraparte do teste anterior: se a lease do pedido AINDA estiver
        # dentro do prazo no momento da reentrega, fechar o run (mesmo que
        # ele por algum motivo não tivesse sido fechado antes) é seguro --
        # lease_ainda_valida é calculada como True porque é genuinamente
        # verdade, não porque foi assumida.
        pedido = self._pedido_em_andamento()
        run_ainda_ativo = pedido.run
        concluido = registrar_resultado_observado(
            pedido, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(seconds=5),
        )
        inconsistente = dataclasses.replace(concluido, run=run_ainda_ativo)
        de_novo = registrar_resultado_observado(
            inconsistente, pedido.lease.lease_token, pedido.lease.generation,
            {"ok": True}, RequestStatus.CONCLUIDO, agora=T0 + timedelta(seconds=10),
        )
        self.assertEqual(de_novo.run.status, AgentRunStatus.CONCLUIDO)


if __name__ == "__main__":
    unittest.main()
