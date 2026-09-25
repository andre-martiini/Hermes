"""Testes de `autonomy/requests.py` — só lógica pura, sem I/O (P04 sub-entrega
1/N: "Implementar os estados, leases e gerações da seção 4" do plano de
autonomia).

Cobre: a máquina de estados de `RequestStatus` (transições permitidas,
terminais nunca transicionam, `ERRO_LEGADO` só como destino inatingível),
emissão/expiração/fencing de `Lease`, e o backoff com jitter.
"""

import unittest
from datetime import datetime, timedelta, timezone

from autonomy.requests import (
    BACKOFF_BASE_SEGUNDOS,
    DEFAULT_LEASE_SEGUNDOS,
    ESTADOS_TERMINAIS,
    Lease,
    RequestStatus,
    calcular_backoff_segundos,
    gerar_lease_token,
    lease_expirada,
    lease_valida_para_acao,
    nova_lease,
    transicoes_permitidas,
    validar_transicao,
)


class TestTransicoesPermitidas(unittest.TestCase):
    def test_pendente_vai_para_reservado_ou_cancelado(self):
        self.assertEqual(
            transicoes_permitidas(RequestStatus.PENDENTE),
            frozenset({RequestStatus.RESERVADO, RequestStatus.CANCELADO}),
        )

    def test_todos_os_terminais_nao_tem_saida(self):
        for terminal in ESTADOS_TERMINAIS:
            with self.subTest(terminal=terminal):
                self.assertEqual(transicoes_permitidas(terminal), frozenset())

    def test_nenhum_estado_transiciona_para_erro_legado(self):
        # ERRO_LEGADO é só para normalizar registros antigos na leitura;
        # nenhum estado novo deve poder produzi-lo.
        for status in RequestStatus:
            with self.subTest(status=status):
                self.assertNotIn(RequestStatus.ERRO_LEGADO, transicoes_permitidas(status))

    def test_resultado_desconhecido_nao_volta_direto_para_em_andamento(self):
        # Seção 4.5, item 8: "operação externa incerta vai para
        # reconciliação" -- nunca retoma direto sem passar por VERIFICANDO.
        self.assertNotIn(
            RequestStatus.EM_ANDAMENTO,
            transicoes_permitidas(RequestStatus.RESULTADO_DESCONHECIDO),
        )

    def test_reservado_nao_pula_para_concluido(self):
        # Achado da 1a rodada de revisão adversarial: só PENDENTE tinha o
        # conjunto exato coberto por teste; nada impedia silenciosamente
        # alguém adicionar um atalho para CONCLUIDO nos demais estados sem
        # quebrar teste nenhum.
        self.assertNotIn(RequestStatus.CONCLUIDO, transicoes_permitidas(RequestStatus.RESERVADO))

    def test_em_andamento_nao_pula_para_concluido(self):
        self.assertNotIn(RequestStatus.CONCLUIDO, transicoes_permitidas(RequestStatus.EM_ANDAMENTO))

    def test_reservado_transicoes_exatas(self):
        self.assertEqual(
            transicoes_permitidas(RequestStatus.RESERVADO),
            frozenset({RequestStatus.EM_ANDAMENTO, RequestStatus.PENDENTE, RequestStatus.CANCELADO}),
        )

    def test_em_andamento_transicoes_exatas(self):
        self.assertEqual(
            transicoes_permitidas(RequestStatus.EM_ANDAMENTO),
            frozenset({
                RequestStatus.VERIFICANDO,
                RequestStatus.AGUARDANDO_APROVACAO,
                RequestStatus.AGUARDANDO_EXTERNO,
                RequestStatus.RETENTATIVA_AGENDADA,
                RequestStatus.RESULTADO_DESCONHECIDO,
                RequestStatus.FALHA_FINAL,
                RequestStatus.CANCELADO,
            }),
        )

    def test_verificando_transicoes_exatas(self):
        self.assertEqual(
            transicoes_permitidas(RequestStatus.VERIFICANDO),
            frozenset({
                RequestStatus.CONCLUIDO,
                RequestStatus.RETENTATIVA_AGENDADA,
                RequestStatus.FALHA_FINAL,
                RequestStatus.RESULTADO_DESCONHECIDO,
            }),
        )

    def test_aguardando_aprovacao_transicoes_exatas(self):
        self.assertEqual(
            transicoes_permitidas(RequestStatus.AGUARDANDO_APROVACAO),
            frozenset({RequestStatus.EM_ANDAMENTO, RequestStatus.CANCELADO}),
        )

    def test_aguardando_externo_transicoes_exatas(self):
        self.assertEqual(
            transicoes_permitidas(RequestStatus.AGUARDANDO_EXTERNO),
            frozenset({
                RequestStatus.EM_ANDAMENTO,
                RequestStatus.VERIFICANDO,
                RequestStatus.RESULTADO_DESCONHECIDO,
                RequestStatus.CANCELADO,
            }),
        )

    def test_retentativa_agendada_transicoes_exatas(self):
        self.assertEqual(
            transicoes_permitidas(RequestStatus.RETENTATIVA_AGENDADA),
            frozenset({
                RequestStatus.RESERVADO,
                RequestStatus.PENDENTE,
                RequestStatus.FALHA_FINAL,
                RequestStatus.CANCELADO,
            }),
        )

    def test_resultado_desconhecido_transicoes_exatas(self):
        self.assertEqual(
            transicoes_permitidas(RequestStatus.RESULTADO_DESCONHECIDO),
            frozenset({
                RequestStatus.VERIFICANDO,
                RequestStatus.RETENTATIVA_AGENDADA,
                RequestStatus.FALHA_FINAL,
            }),
        )


class TestValidarTransicao(unittest.TestCase):
    def test_transicao_permitida_e_valida(self):
        ok, motivo = validar_transicao(RequestStatus.PENDENTE, RequestStatus.RESERVADO)
        self.assertTrue(ok)
        self.assertEqual(motivo, "")

    def test_transicao_nao_permitida_e_invalida(self):
        ok, motivo = validar_transicao(RequestStatus.PENDENTE, RequestStatus.CONCLUIDO)
        self.assertFalse(ok)
        self.assertIn("não é permitida", motivo)

    def test_mesmo_estado_e_invalido(self):
        ok, motivo = validar_transicao(RequestStatus.EM_ANDAMENTO, RequestStatus.EM_ANDAMENTO)
        self.assertFalse(ok)
        self.assertIn("já está em", motivo)

    def test_terminal_nunca_transiciona(self):
        ok, motivo = validar_transicao(RequestStatus.CONCLUIDO, RequestStatus.PENDENTE)
        self.assertFalse(ok)
        self.assertIn("terminal", motivo)

    def test_falha_final_nunca_transiciona(self):
        ok, _ = validar_transicao(RequestStatus.FALHA_FINAL, RequestStatus.RESERVADO)
        self.assertFalse(ok)

    def test_cancelado_nunca_transiciona(self):
        ok, _ = validar_transicao(RequestStatus.CANCELADO, RequestStatus.PENDENTE)
        self.assertFalse(ok)

    def test_erro_legado_nunca_transiciona(self):
        ok, _ = validar_transicao(RequestStatus.ERRO_LEGADO, RequestStatus.PENDENTE)
        self.assertFalse(ok)

    def test_verificando_para_concluido_e_valido(self):
        ok, _ = validar_transicao(RequestStatus.VERIFICANDO, RequestStatus.CONCLUIDO)
        self.assertTrue(ok)


class TestGerarLeaseToken(unittest.TestCase):
    def test_dois_tokens_sao_diferentes(self):
        self.assertNotEqual(gerar_lease_token(), gerar_lease_token())

    def test_token_nao_e_vazio(self):
        self.assertTrue(gerar_lease_token())


class TestNovaLease(unittest.TestCase):
    def test_primeira_reserva_gera_geracao_1(self):
        agora = datetime(2026, 1, 1, tzinfo=timezone.utc)
        lease = nova_lease("executor-a", generation_anterior=0, agora=agora)
        self.assertEqual(lease.generation, 1)
        self.assertEqual(lease.executor_id, "executor-a")
        self.assertEqual(lease.expires_at, agora + timedelta(seconds=DEFAULT_LEASE_SEGUNDOS))

    def test_reserva_seguinte_incrementa_geracao(self):
        agora = datetime(2026, 1, 1, tzinfo=timezone.utc)
        lease = nova_lease("executor-b", generation_anterior=5, agora=agora)
        self.assertEqual(lease.generation, 6)

    def test_duracao_customizada(self):
        agora = datetime(2026, 1, 1, tzinfo=timezone.utc)
        lease = nova_lease("executor-c", generation_anterior=0, agora=agora, duracao_segundos=30)
        self.assertEqual(lease.expires_at, agora + timedelta(seconds=30))

    def test_executor_id_vazio_e_erro(self):
        with self.assertRaises(ValueError):
            nova_lease("", generation_anterior=0)

    def test_executor_id_so_espacos_e_erro(self):
        with self.assertRaises(ValueError):
            nova_lease("   ", generation_anterior=0)

    def test_duracao_zero_e_erro(self):
        with self.assertRaises(ValueError):
            nova_lease("executor-d", generation_anterior=0, duracao_segundos=0)

    def test_duracao_negativa_e_erro(self):
        with self.assertRaises(ValueError):
            nova_lease("executor-e", generation_anterior=0, duracao_segundos=-1)

    def test_geracao_anterior_negativa_e_erro(self):
        with self.assertRaises(ValueError):
            nova_lease("executor-f", generation_anterior=-1)

    def test_agora_omitido_usa_relogio_real(self):
        antes = datetime.now(timezone.utc)
        lease = nova_lease("executor-g", generation_anterior=0)
        depois = datetime.now(timezone.utc)
        self.assertTrue(antes <= lease.expires_at - timedelta(seconds=DEFAULT_LEASE_SEGUNDOS) <= depois)


class TestLeaseExpirada(unittest.TestCase):
    def test_antes_do_vencimento_nao_expirada(self):
        expira = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        lease = Lease("tok", 1, "executor-a", expira)
        agora = expira - timedelta(seconds=1)
        self.assertFalse(lease_expirada(lease, agora=agora))

    def test_exatamente_no_vencimento_e_expirada(self):
        expira = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        lease = Lease("tok", 1, "executor-a", expira)
        self.assertTrue(lease_expirada(lease, agora=expira))

    def test_depois_do_vencimento_e_expirada(self):
        expira = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        lease = Lease("tok", 1, "executor-a", expira)
        agora = expira + timedelta(seconds=1)
        self.assertTrue(lease_expirada(lease, agora=agora))


class TestLeaseValidaParaAcao(unittest.TestCase):
    def setUp(self):
        self.expira = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        self.lease = Lease("token-real", 3, "executor-a", self.expira)

    def test_token_e_geracao_corretos_e_dentro_do_prazo(self):
        agora = self.expira - timedelta(seconds=1)
        ok, motivo = lease_valida_para_acao(self.lease, "token-real", 3, agora=agora)
        self.assertTrue(ok)
        self.assertEqual(motivo, "")

    def test_lease_none_e_invalida(self):
        ok, motivo = lease_valida_para_acao(None, "token-real", 3)
        self.assertFalse(ok)
        self.assertIn("nenhuma reserva", motivo)

    def test_lease_expirada_e_invalida_mesmo_com_token_certo(self):
        ok, motivo = lease_valida_para_acao(self.lease, "token-real", 3, agora=self.expira)
        self.assertFalse(ok)
        self.assertIn("expirada", motivo)

    def test_geracao_errada_e_invalida(self):
        agora = self.expira - timedelta(seconds=1)
        ok, motivo = lease_valida_para_acao(self.lease, "token-real", 2, agora=agora)
        self.assertFalse(ok)
        self.assertIn("geração não confere", motivo)

    def test_token_errado_e_invalido(self):
        agora = self.expira - timedelta(seconds=1)
        ok, motivo = lease_valida_para_acao(self.lease, "token-impostor", 3, agora=agora)
        self.assertFalse(ok)
        self.assertIn("token de reserva não confere", motivo)

    def test_token_vazio_e_invalido(self):
        agora = self.expira - timedelta(seconds=1)
        ok, _ = lease_valida_para_acao(self.lease, "", 3, agora=agora)
        self.assertFalse(ok)


class TestLeaseValidaParaAcaoInputsAdversariais(unittest.TestCase):
    """Achados da 1a rodada de revisão adversarial (P04 sub-entrega 1/N):
    `token_apresentado`/`generation_apresentada` vêm de um consumidor
    externo -- entrada malformada/adversarial nunca deve escapar como
    exceção não tratada, só como "não confere"."""

    def setUp(self):
        self.expira = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        self.lease = Lease("token-real", 3, "executor-a", self.expira)
        self.agora = self.expira - timedelta(seconds=1)

    def test_token_nao_ascii_nao_lanca_excecao(self):
        # secrets.compare_digest levanta TypeError para strings não-ASCII;
        # sem tratamento, isto vazava como um crash em vez de reprovar.
        ok, motivo = lease_valida_para_acao(self.lease, "token-ção-não-confere", 3, agora=self.agora)
        self.assertFalse(ok)
        self.assertIn("token de reserva não confere", motivo)

    def test_generation_nao_numerica_nao_lanca_excecao(self):
        ok, motivo = lease_valida_para_acao(self.lease, "token-real", "nao-numero", agora=self.agora)
        self.assertFalse(ok)
        self.assertIn("geração", motivo)

    def test_generation_none_nao_lanca_excecao(self):
        ok, _ = lease_valida_para_acao(self.lease, "token-real", None, agora=self.agora)
        self.assertFalse(ok)

    def test_generation_string_com_fracao_e_invalida_sem_lancar(self):
        # int("3.5") levanta ValueError -- mesmo tratamento dos demais
        # valores não inteiros, nunca deve escapar como exceção.
        ok, motivo = lease_valida_para_acao(self.lease, "token-real", "3.5", agora=self.agora)
        self.assertFalse(ok)
        self.assertIn("geração", motivo)

    def test_generation_infinito_positivo_nao_lanca_excecao(self):
        # Achado da 2a rodada de revisão adversarial: int(float("inf"))
        # levanta OverflowError, não TypeError/ValueError -- json.loads
        # aceita "Infinity" como extensão por padrão, então um consumidor
        # podia mandar isso num payload e crashar esta função.
        ok, motivo = lease_valida_para_acao(self.lease, "token-real", float("inf"), agora=self.agora)
        self.assertFalse(ok)
        self.assertIn("geração", motivo)

    def test_generation_infinito_negativo_nao_lanca_excecao(self):
        ok, motivo = lease_valida_para_acao(self.lease, "token-real", float("-inf"), agora=self.agora)
        self.assertFalse(ok)
        self.assertIn("geração", motivo)

    def test_generation_decimal_infinito_nao_lanca_excecao(self):
        from decimal import Decimal

        ok, motivo = lease_valida_para_acao(self.lease, "token-real", Decimal("Infinity"), agora=self.agora)
        self.assertFalse(ok)
        self.assertIn("geração", motivo)


class TestTzAware(unittest.TestCase):
    """Achado da 1a rodada de revisão adversarial (P04 sub-entrega 1/N): um
    datetime "naive" (sem timezone) em `agora`/`expires_at` deve falhar cedo
    e com mensagem clara, não como TypeError de comparação distante da causa
    raiz."""

    def test_nova_lease_agora_naive_e_erro(self):
        with self.assertRaises(ValueError):
            nova_lease("executor-a", generation_anterior=0, agora=datetime(2026, 1, 1))

    def test_lease_expirada_agora_naive_e_erro(self):
        lease = Lease("tok", 1, "executor-a", datetime(2026, 1, 1, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            lease_expirada(lease, agora=datetime(2026, 1, 1))

    def test_lease_valida_para_acao_agora_naive_e_erro(self):
        lease = Lease("tok", 1, "executor-a", datetime(2026, 1, 1, tzinfo=timezone.utc))
        with self.assertRaises(ValueError):
            lease_valida_para_acao(lease, "tok", 1, agora=datetime(2026, 1, 1))

    def test_lease_construida_com_expires_at_naive_e_erro(self):
        with self.assertRaises(ValueError):
            Lease("tok", 1, "executor-a", datetime(2026, 1, 1))


class _RngFixo:
    """Fake mínimo de `random.Random` para teste determinístico do jitter."""

    def __init__(self, valor: float):
        self._valor = valor

    def uniform(self, a: float, b: float) -> float:
        return self._valor


class TestCalcularBackoffSegundos(unittest.TestCase):
    def test_tentativa_1_usa_primeiro_patamar_sem_jitter(self):
        segundos = calcular_backoff_segundos(1, rng=_RngFixo(0.0))
        self.assertEqual(segundos, BACKOFF_BASE_SEGUNDOS[0])

    def test_tentativa_2_usa_segundo_patamar(self):
        segundos = calcular_backoff_segundos(2, rng=_RngFixo(0.0))
        self.assertEqual(segundos, BACKOFF_BASE_SEGUNDOS[1])

    def test_tentativa_3_usa_terceiro_patamar(self):
        segundos = calcular_backoff_segundos(3, rng=_RngFixo(0.0))
        self.assertEqual(segundos, BACKOFF_BASE_SEGUNDOS[2])

    def test_tentativa_alem_do_maior_patamar_reusa_o_ultimo(self):
        segundos = calcular_backoff_segundos(10, rng=_RngFixo(0.0))
        self.assertEqual(segundos, BACKOFF_BASE_SEGUNDOS[-1])

    def test_jitter_positivo_aumenta_o_valor(self):
        segundos = calcular_backoff_segundos(1, rng=_RngFixo(0.2))
        self.assertEqual(segundos, BACKOFF_BASE_SEGUNDOS[0] * 1.2)

    def test_jitter_negativo_no_patamar_minimo_nao_fica_abaixo_do_piso(self):
        # -20% de 60s = 48s, bem acima do piso de 1s -- não exercita o
        # max(1.0, ...) de verdade, só confirma o caso normal do jitter
        # dentro da faixa esperada. O piso em si é exercitado pelo teste
        # seguinte.
        segundos = calcular_backoff_segundos(1, rng=_RngFixo(-0.2))
        self.assertEqual(segundos, BACKOFF_BASE_SEGUNDOS[0] * 0.8)

    def test_jitter_extremo_negativo_atinge_o_piso_de_1_segundo(self):
        # Achado da 1a rodada de revisão adversarial (P04 sub-entrega 1/N):
        # nenhum teste chamava calcular_backoff_segundos com um `rng` que
        # realmente disparasse o max(1.0, ...) -- com JITTER_FRACAO=0.2 e
        # rng real (uniform(-0.2, 0.2)) o piso é inatingível na prática; um
        # rng fake fora da faixa normal (-1.0) prova que o piso funciona se
        # algum dia for chamado com jitter maior.
        segundos = calcular_backoff_segundos(1, rng=_RngFixo(-1.0))
        self.assertEqual(segundos, 1.0)

    def test_tentativa_zero_e_erro(self):
        with self.assertRaises(ValueError):
            calcular_backoff_segundos(0)

    def test_tentativa_negativa_e_erro(self):
        with self.assertRaises(ValueError):
            calcular_backoff_segundos(-1)

    def test_rng_omitido_usa_secrets_systemrandom(self):
        # Sem rng explícito, o resultado deve continuar dentro da faixa de
        # jitter declarada (não trava, não estoura o range).
        segundos = calcular_backoff_segundos(1)
        piso = BACKOFF_BASE_SEGUNDOS[0] * (1 - 0.2)
        teto = BACKOFF_BASE_SEGUNDOS[0] * (1 + 0.2)
        self.assertTrue(piso <= segundos <= teto)


if __name__ == "__main__":
    unittest.main()
