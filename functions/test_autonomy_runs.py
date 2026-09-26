"""Testes de `autonomy/runs.py` -- só lógica pura, sem I/O (P04 do plano de
autonomia, passo 2 do pacote: "servidor cria agent_run ao reservar/iniciar;
conclusão e timeout são transições verificadas, não simples add de
resumo").
"""

import unittest
from datetime import datetime, timedelta, timezone

from autonomy.runs import (
    AgentRun,
    AgentRunStatus,
    RunFinalizado,
    RunLeaseInvalida,
    concluir_run,
    criar_run,
    expirar_por_timeout,
    marcar_em_andamento,
    run_esta_ativo,
    transicoes_permitidas,
)

T0 = datetime(2026, 9, 26, 9, 0, 0, tzinfo=timezone.utc)
LEASE_TOKEN = "tok-abc123"
GENERATION = 1


def _run(status: AgentRunStatus = AgentRunStatus.INICIADO, **kwargs) -> AgentRun:
    defaults = dict(
        run_id="run-1",
        request_id="req-1",
        executor_id="executor-a",
        lease_token=LEASE_TOKEN,
        generation=GENERATION,
        status=status,
        iniciado_em=T0,
    )
    defaults.update(kwargs)
    return AgentRun(**defaults)


class TestAgentRunConstrucao(unittest.TestCase):
    def test_campos_obrigatorios_vazios_rejeitados(self):
        for campo in ("run_id", "request_id", "executor_id", "lease_token"):
            with self.assertRaises(ValueError):
                _run(**{campo: "   "})

    def test_generation_menor_que_1_rejeitada(self):
        with self.assertRaises(ValueError):
            _run(generation=0)

    def test_generation_nao_inteira_rejeitada_com_value_error(self):
        # Achado de revisão adversarial: um generation não coercível (aqui
        # nem sequer numérico) devia levantar ValueError, não TypeError
        # vazando de uma comparação "<" sem coerção prévia.
        with self.assertRaises(ValueError):
            _run(generation="abc")

    def test_generation_string_numerica_e_coagida_para_int(self):
        run = _run(generation="3")
        self.assertEqual(run.generation, 3)
        self.assertIsInstance(run.generation, int)

    def test_iniciado_em_naive_rejeitado(self):
        with self.assertRaises(ValueError):
            _run(iniciado_em=datetime(2026, 9, 26, 9, 0, 0))

    def test_finalizado_em_naive_rejeitado(self):
        with self.assertRaises(ValueError):
            _run(finalizado_em=datetime(2026, 9, 26, 9, 5, 0))

    def test_campos_sao_normalizados(self):
        run = _run(run_id="  run-1  ", request_id=" req-1 ", executor_id=" executor-a ")
        self.assertEqual(run.run_id, "run-1")
        self.assertEqual(run.request_id, "req-1")
        self.assertEqual(run.executor_id, "executor-a")

    def test_estado_inicial(self):
        run = _run()
        self.assertEqual(run.status, AgentRunStatus.INICIADO)
        self.assertIsNone(run.finalizado_em)
        self.assertIsNone(run.resultado)
        self.assertTrue(run_esta_ativo(run))


class TestCriarRun(unittest.TestCase):
    def test_cria_run_iniciado(self):
        run = criar_run("run-1", "req-1", "executor-a", LEASE_TOKEN, GENERATION, agora=T0)
        self.assertEqual(run.status, AgentRunStatus.INICIADO)
        self.assertEqual(run.iniciado_em, T0)
        self.assertEqual(run.generation, GENERATION)

    def test_cria_run_normaliza_timezone_para_utc(self):
        fuso_menos3 = timezone(timedelta(hours=-3))
        agora_local = datetime(2026, 9, 26, 6, 0, 0, tzinfo=fuso_menos3)
        run = criar_run("run-1", "req-1", "executor-a", LEASE_TOKEN, GENERATION, agora=agora_local)
        self.assertEqual(run.iniciado_em, T0)
        self.assertEqual(run.iniciado_em.tzinfo, timezone.utc)

    def test_cria_run_agora_naive_rejeitado(self):
        with self.assertRaises(ValueError):
            criar_run("run-1", "req-1", "executor-a", LEASE_TOKEN, GENERATION, agora=datetime(2026, 9, 26))


class TestMarcarEmAndamento(unittest.TestCase):
    def test_transiciona_de_iniciado(self):
        run = marcar_em_andamento(_run(), LEASE_TOKEN, GENERATION)
        self.assertEqual(run.status, AgentRunStatus.EM_ANDAMENTO)

    def test_repetido_e_idempotente(self):
        run = _run(status=AgentRunStatus.EM_ANDAMENTO)
        de_novo = marcar_em_andamento(run, LEASE_TOKEN, GENERATION)
        self.assertEqual(de_novo, run)

    def test_token_errado_rejeitado(self):
        with self.assertRaises(RunLeaseInvalida):
            marcar_em_andamento(_run(), "tok-errado", GENERATION)

    def test_geracao_errada_rejeitada(self):
        with self.assertRaises(RunLeaseInvalida):
            marcar_em_andamento(_run(), LEASE_TOKEN, GENERATION + 1)

    def test_geracao_nao_inteira_rejeitada(self):
        with self.assertRaises(RunLeaseInvalida):
            marcar_em_andamento(_run(), LEASE_TOKEN, "abc")

    def test_run_terminal_rejeitado(self):
        run = _run(status=AgentRunStatus.CONCLUIDO, finalizado_em=T0)
        with self.assertRaises(RunFinalizado):
            marcar_em_andamento(run, LEASE_TOKEN, GENERATION)

    def test_repetido_com_token_errado_ainda_e_rejeitado(self):
        # O atalho idempotente (já EM_ANDAMENTO) não pode pular o fencing --
        # achado de revisão adversarial, verificado como já correto no
        # código, só faltava o teste que prova isso.
        run = _run(status=AgentRunStatus.EM_ANDAMENTO)
        with self.assertRaises(RunLeaseInvalida):
            marcar_em_andamento(run, "tok-errado", GENERATION)


class TestConcluirRun(unittest.TestCase):
    def test_conclui_a_partir_de_em_andamento(self):
        run = _run(status=AgentRunStatus.EM_ANDAMENTO)
        concluido = concluir_run(
            run, LEASE_TOKEN, GENERATION, AgentRunStatus.CONCLUIDO,
            lease_ainda_valida=True, resultado={"ok": True}, agora=T0 + timedelta(minutes=2),
        )
        self.assertEqual(concluido.status, AgentRunStatus.CONCLUIDO)
        self.assertEqual(concluido.resultado, {"ok": True})
        self.assertEqual(concluido.finalizado_em, T0 + timedelta(minutes=2))

    def test_falha_a_partir_de_iniciado_sem_checkpoint(self):
        # Uma tentativa pode falhar antes de qualquer marcar_em_andamento.
        run = _run(status=AgentRunStatus.INICIADO)
        falho = concluir_run(
            run, LEASE_TOKEN, GENERATION, AgentRunStatus.FALHA,
            lease_ainda_valida=True, resultado="erro X",
        )
        self.assertEqual(falho.status, AgentRunStatus.FALHA)

    def test_conclui_a_partir_de_iniciado_sem_checkpoint(self):
        # Simétrico ao caso de FALHA acima -- CONCLUIDO direto de INICIADO
        # também é uma aresta permitida em _TRANSICOES_PERMITIDAS e não
        # tinha teste cobrindo especificamente este destino.
        run = _run(status=AgentRunStatus.INICIADO)
        concluido = concluir_run(
            run, LEASE_TOKEN, GENERATION, AgentRunStatus.CONCLUIDO,
            lease_ainda_valida=True, resultado="ok",
        )
        self.assertEqual(concluido.status, AgentRunStatus.CONCLUIDO)

    def test_novo_status_timeout_rejeitado(self):
        run = _run(status=AgentRunStatus.EM_ANDAMENTO)
        with self.assertRaises(ValueError):
            concluir_run(run, LEASE_TOKEN, GENERATION, AgentRunStatus.TIMEOUT, lease_ainda_valida=True)

    def test_token_errado_rejeitado(self):
        run = _run(status=AgentRunStatus.EM_ANDAMENTO)
        with self.assertRaises(RunLeaseInvalida):
            concluir_run(run, "tok-errado", GENERATION, AgentRunStatus.CONCLUIDO, lease_ainda_valida=True)

    def test_lease_do_pedido_nao_mais_atual_rejeitada(self):
        # Achado de revisão adversarial (Codex, PR #336, P1): identidade do
        # RUN (token/geração deste AgentRun especificamente) não é suficiente
        # para uma conclusão NOVA -- o executor pode ter perdido a reserva do
        # PEDIDO (lease expirada/substituída por geração mais nova) e ainda
        # assim apresentar credenciais que batem com as deste run antigo.
        run = _run(status=AgentRunStatus.EM_ANDAMENTO)
        with self.assertRaises(RunLeaseInvalida):
            concluir_run(
                run, LEASE_TOKEN, GENERATION, AgentRunStatus.CONCLUIDO,
                lease_ainda_valida=False, resultado="tarde demais",
            )

    def test_reentrega_mesmo_resultado_e_idempotente(self):
        run = _run(status=AgentRunStatus.CONCLUIDO, resultado={"ok": True}, finalizado_em=T0)
        de_novo = concluir_run(
            run, LEASE_TOKEN, GENERATION, AgentRunStatus.CONCLUIDO,
            lease_ainda_valida=True, resultado={"ok": True},
        )
        self.assertEqual(de_novo, run)

    def test_reentrega_nao_exige_lease_do_pedido_ainda_valida(self):
        # Diferente de uma conclusão NOVA: reentrega do MESMO resultado já
        # registrado é aceita mesmo com lease_ainda_valida=False -- mesma
        # razão de autonomy.execution.registrar_resultado_observado (uma
        # resposta perdida por timeout de rede pode chegar bem depois do
        # pedido já ter sido reatribuído a outra geração).
        run = _run(status=AgentRunStatus.CONCLUIDO, resultado={"ok": True}, finalizado_em=T0)
        de_novo = concluir_run(
            run, LEASE_TOKEN, GENERATION, AgentRunStatus.CONCLUIDO,
            lease_ainda_valida=False, resultado={"ok": True},
        )
        self.assertEqual(de_novo, run)

    def test_reentrega_resultado_diferente_rejeitada(self):
        run = _run(status=AgentRunStatus.CONCLUIDO, resultado={"ok": True}, finalizado_em=T0)
        with self.assertRaises(RunFinalizado):
            concluir_run(
                run, LEASE_TOKEN, GENERATION, AgentRunStatus.CONCLUIDO,
                lease_ainda_valida=True, resultado={"ok": False},
            )

    def test_reentrega_status_terminal_diferente_rejeitada(self):
        run = _run(status=AgentRunStatus.CONCLUIDO, resultado={"ok": True}, finalizado_em=T0)
        with self.assertRaises(RunFinalizado):
            concluir_run(
                run, LEASE_TOKEN, GENERATION, AgentRunStatus.FALHA,
                lease_ainda_valida=True, resultado={"ok": True},
            )

    def test_reentrega_terminal_ainda_exige_fencing(self):
        # Achado a evitar: reentrega idempotente não pode pular a checagem
        # de identidade -- um token errado nunca deveria "confirmar" nada,
        # mesmo que o resultado batesse.
        run = _run(status=AgentRunStatus.CONCLUIDO, resultado={"ok": True}, finalizado_em=T0)
        with self.assertRaises(RunLeaseInvalida):
            concluir_run(
                run, "tok-errado", GENERATION, AgentRunStatus.CONCLUIDO,
                lease_ainda_valida=True, resultado={"ok": True},
            )

    def test_timeout_para_terminal_diferente_rejeitado(self):
        run = _run(status=AgentRunStatus.TIMEOUT, finalizado_em=T0)
        with self.assertRaises(RunFinalizado):
            concluir_run(
                run, LEASE_TOKEN, GENERATION, AgentRunStatus.CONCLUIDO,
                lease_ainda_valida=True, resultado=None,
            )

    def test_resultado_bool_e_int_nao_sao_o_mesmo_valor_na_reentrega(self):
        # Achado de revisão adversarial (Codex, PR #336, P2): "==" trata
        # True/1 como iguais, o que faria uma reentrega com o tipo trocado
        # ser aceita como "mesmo resultado" -- _mesmo_valor_canonico (via
        # serialização) distingue os dois, mesma regra de autonomy.ledger.
        run = _run(status=AgentRunStatus.CONCLUIDO, resultado=True, finalizado_em=T0)
        with self.assertRaises(RunFinalizado):
            concluir_run(
                run, LEASE_TOKEN, GENERATION, AgentRunStatus.CONCLUIDO,
                lease_ainda_valida=True, resultado=1,
            )

    def test_resultado_dict_mutavel_do_chamador_nao_afeta_run_guardado(self):
        # Achado de revisão adversarial (Codex, PR #336, P2): resultado
        # guardado por referência permitia mutar o desfecho "terminal" sem
        # nenhuma transição -- o snapshot em __post_init__ fecha essa porta.
        resultado_original = {"contador": 1}
        run = _run(status=AgentRunStatus.EM_ANDAMENTO)
        concluido = concluir_run(
            run, LEASE_TOKEN, GENERATION, AgentRunStatus.CONCLUIDO,
            lease_ainda_valida=True, resultado=resultado_original,
        )
        resultado_original["contador"] = 999
        self.assertEqual(concluido.resultado, {"contador": 1})
        with self.assertRaises(TypeError):
            concluido.resultado["contador"] = 2


class TestExpirarPorTimeout(unittest.TestCase):
    def test_expira_run_ativo_com_lease_vencida(self):
        run = _run(status=AgentRunStatus.EM_ANDAMENTO)
        expirado = expirar_por_timeout(run, lease_expirada=True, agora=T0 + timedelta(minutes=6))
        self.assertEqual(expirado.status, AgentRunStatus.TIMEOUT)
        self.assertEqual(expirado.finalizado_em, T0 + timedelta(minutes=6))

    def test_expira_run_iniciado_sem_checkpoint(self):
        run = _run(status=AgentRunStatus.INICIADO)
        expirado = expirar_por_timeout(run, lease_expirada=True)
        self.assertEqual(expirado.status, AgentRunStatus.TIMEOUT)

    def test_nao_expira_sem_lease_realmente_vencida(self):
        run = _run(status=AgentRunStatus.EM_ANDAMENTO)
        with self.assertRaises(ValueError):
            expirar_por_timeout(run, lease_expirada=False)

    def test_run_ja_terminal_diferente_rejeitado(self):
        run = _run(status=AgentRunStatus.CONCLUIDO, finalizado_em=T0)
        with self.assertRaises(RunFinalizado):
            expirar_por_timeout(run, lease_expirada=True)

    def test_timeout_repetido_e_idempotente(self):
        run = _run(status=AgentRunStatus.TIMEOUT, finalizado_em=T0)
        de_novo = expirar_por_timeout(run, lease_expirada=True)
        self.assertEqual(de_novo, run)

    def test_nao_exige_token_nem_geracao(self):
        # Ação de sistema (sweep) -- não recebe credenciais de executor.
        run = _run(status=AgentRunStatus.EM_ANDAMENTO)
        expirado = expirar_por_timeout(run, lease_expirada=True)
        self.assertEqual(expirado.status, AgentRunStatus.TIMEOUT)


class TestTransicoesPermitidas(unittest.TestCase):
    def test_terminal_nao_tem_saida(self):
        for status in (AgentRunStatus.CONCLUIDO, AgentRunStatus.FALHA, AgentRunStatus.TIMEOUT):
            self.assertEqual(transicoes_permitidas(status), frozenset())

    def test_iniciado_permite_todos_os_terminais_e_em_andamento(self):
        permitidas = transicoes_permitidas(AgentRunStatus.INICIADO)
        self.assertEqual(
            permitidas,
            frozenset({
                AgentRunStatus.EM_ANDAMENTO,
                AgentRunStatus.CONCLUIDO,
                AgentRunStatus.FALHA,
                AgentRunStatus.TIMEOUT,
            }),
        )


class TestRunEstaAtivo(unittest.TestCase):
    def test_ativo_para_nao_terminais(self):
        self.assertTrue(run_esta_ativo(_run(status=AgentRunStatus.INICIADO)))
        self.assertTrue(run_esta_ativo(_run(status=AgentRunStatus.EM_ANDAMENTO)))

    def test_inativo_para_terminais(self):
        for status in (AgentRunStatus.CONCLUIDO, AgentRunStatus.FALHA, AgentRunStatus.TIMEOUT):
            run = _run(status=status, finalizado_em=T0)
            self.assertFalse(run_esta_ativo(run))


if __name__ == "__main__":
    unittest.main()
