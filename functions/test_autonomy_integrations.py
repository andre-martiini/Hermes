"""Testes de `autonomy/integrations.py` — só lógica pura, sem I/O (P05
sub-entrega 2/N: passo 7 do pacote, "Publicar heartbeat/cobertura por
integração, com estado healthy/degraded/unavailable/unknown...").

Cobre: `calcular_lag_segundos` (uso de coverage_until vs. last_success_at,
None quando nenhum dos dois, rejeição de heartbeat anterior à referência),
`calcular_status_integracao` (as 4 saídas e suas prioridades, thresholds
inclusivos/invertidos), e `IntegrationHealth`/`montar_saude_integracao`
(consistência forçada de lag_seconds/status, congelamento de capabilities,
timezone-awareness, imutabilidade)."""

import unittest
from datetime import datetime, timedelta, timezone

from autonomy.integrations import (
    DEFAULT_LIMITE_DEGRADADO_SEGUNDOS,
    DEFAULT_LIMITE_INDISPONIVEL_SEGUNDOS,
    IntegrationHealth,
    IntegrationStatus,
    calcular_lag_segundos,
    calcular_status_integracao,
    montar_saude_integracao,
)

_AGORA = datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc)
_NAIVE = datetime(2026, 9, 28, 12, 0, 0)


class TestIntegrationStatus(unittest.TestCase):
    def test_quatro_estados_do_passo_7_do_pacote(self):
        self.assertEqual(len(IntegrationStatus), 4)
        self.assertEqual(
            {s.value for s in IntegrationStatus},
            {"healthy", "degraded", "unavailable", "unknown"},
        )


class TestCalcularLagSegundos(unittest.TestCase):
    def test_nenhuma_referencia_devolve_none(self):
        self.assertIsNone(calcular_lag_segundos(_AGORA, None, None))

    def test_usa_last_success_at_quando_coverage_ausente(self):
        referencia = _AGORA - timedelta(seconds=120)
        self.assertEqual(calcular_lag_segundos(_AGORA, referencia, None), 120.0)

    def test_prefere_coverage_until_sobre_last_success_at(self):
        last_success = _AGORA - timedelta(seconds=10)
        coverage = _AGORA - timedelta(seconds=500)
        self.assertEqual(
            calcular_lag_segundos(_AGORA, last_success, coverage), 500.0
        )

    def test_lag_zero_quando_referencia_igual_a_heartbeat(self):
        self.assertEqual(calcular_lag_segundos(_AGORA, _AGORA, None), 0.0)

    def test_referencia_no_futuro_levanta_value_error(self):
        futuro = _AGORA + timedelta(seconds=1)
        with self.assertRaises(ValueError):
            calcular_lag_segundos(_AGORA, futuro, None)

    def test_heartbeat_naive_levanta_value_error(self):
        with self.assertRaises(ValueError):
            calcular_lag_segundos(_NAIVE, None, None)

    def test_last_success_naive_levanta_value_error(self):
        with self.assertRaises(ValueError):
            calcular_lag_segundos(_AGORA, _NAIVE, None)

    def test_coverage_naive_levanta_value_error(self):
        with self.assertRaises(ValueError):
            calcular_lag_segundos(_AGORA, None, _NAIVE)

    def test_last_success_naive_e_rejeitado_mesmo_quando_coverage_valido_e_usado(self):
        # Achado de revisão adversarial (P05 sub-entrega 2/N): last_success_at
        # não é a referência usada quando coverage_until está presente, mas
        # ainda assim deve ser validado -- não pode "passar despercebido" só
        # porque não foi o campo escolhido para o cálculo do lag.
        with self.assertRaises(ValueError):
            calcular_lag_segundos(_AGORA, _NAIVE, _AGORA - timedelta(seconds=10))

    def test_last_success_no_futuro_rejeitado_mesmo_quando_coverage_e_a_referencia(self):
        # Achado real de revisão automática do Codex (P2) na PR desta
        # sub-entrega: quando coverage_until domina o cálculo (é a
        # referência usada), last_success_at nunca era comparado a
        # heartbeat_at -- um last_success_at POSTERIOR ao próprio heartbeat
        # que resume o estado passava despercebido.
        heartbeat = _AGORA
        coverage_valido = _AGORA - timedelta(hours=1)
        last_success_no_futuro = _AGORA + timedelta(hours=1)
        with self.assertRaises(ValueError):
            calcular_lag_segundos(heartbeat, last_success_no_futuro, coverage_valido)

    def test_coverage_no_futuro_rejeitado_mesmo_quando_last_success_e_a_referencia(self):
        # Caso simétrico: coverage_until no futuro quando last_success_at
        # (sem coverage_until) é que domina o cálculo -- coberto pelo mesmo
        # loop de validação incondicional.
        heartbeat = _AGORA
        with self.assertRaises(ValueError):
            calcular_lag_segundos(heartbeat, None, _AGORA + timedelta(hours=1))

    def test_lag_correto_atraves_de_fallback_de_dst(self):
        # Achado real de revisão automática do Codex (P2) na PR desta
        # sub-entrega, mesma classe de bug já corrigida em
        # autonomy/requests.py (nova_lease, achado do Codex na PR #326):
        # datetime - datetime com os dois operandos num fuso ciente de DST
        # (ZoneInfo) faz aritmética de relógio de parede, não de tempo
        # decorrido. 01:15 (fold=0, ainda EDT/UTC-4) até 01:45 (fold=1, já
        # EST/UTC-5) em America/New_York é 1h30 (5400s) de tempo real
        # decorrido -- o fallback de DST de 2026-11-01 acontece no meio --
        # mas só 30min (1800s) de diferença de relógio de parede.
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("America/New_York")
        referencia = datetime(2026, 11, 1, 1, 15, tzinfo=tz, fold=0)
        heartbeat = datetime(2026, 11, 1, 1, 45, tzinfo=tz, fold=1)
        lag = calcular_lag_segundos(heartbeat, referencia, None)
        self.assertEqual(lag, 5400.0)


class TestCalcularStatusIntegracao(unittest.TestCase):
    def test_error_code_sempre_unavailable_mesmo_com_leitura_recente(self):
        status = calcular_status_integracao(
            heartbeat_at=_AGORA,
            last_success_at=_AGORA,
            coverage_until=None,
            error_code="timeout",
        )
        self.assertEqual(status, IntegrationStatus.UNAVAILABLE)

    def test_sem_leitura_e_sem_erro_e_unknown(self):
        status = calcular_status_integracao(
            heartbeat_at=_AGORA,
            last_success_at=None,
            coverage_until=None,
            error_code=None,
        )
        self.assertEqual(status, IntegrationStatus.UNKNOWN)

    def test_lag_dentro_do_limite_degradado_e_healthy(self):
        referencia = _AGORA - timedelta(seconds=DEFAULT_LIMITE_DEGRADADO_SEGUNDOS)
        status = calcular_status_integracao(
            heartbeat_at=_AGORA,
            last_success_at=referencia,
            coverage_until=None,
            error_code=None,
        )
        self.assertEqual(status, IntegrationStatus.HEALTHY)

    def test_lag_logo_apos_limite_degradado_e_degraded(self):
        referencia = _AGORA - timedelta(seconds=DEFAULT_LIMITE_DEGRADADO_SEGUNDOS + 1)
        status = calcular_status_integracao(
            heartbeat_at=_AGORA,
            last_success_at=referencia,
            coverage_until=None,
            error_code=None,
        )
        self.assertEqual(status, IntegrationStatus.DEGRADED)

    def test_lag_no_limite_indisponivel_ainda_e_degraded(self):
        referencia = _AGORA - timedelta(seconds=DEFAULT_LIMITE_INDISPONIVEL_SEGUNDOS)
        status = calcular_status_integracao(
            heartbeat_at=_AGORA,
            last_success_at=referencia,
            coverage_until=None,
            error_code=None,
        )
        self.assertEqual(status, IntegrationStatus.DEGRADED)

    def test_lag_alem_do_limite_indisponivel_e_unavailable(self):
        referencia = _AGORA - timedelta(seconds=DEFAULT_LIMITE_INDISPONIVEL_SEGUNDOS + 1)
        status = calcular_status_integracao(
            heartbeat_at=_AGORA,
            last_success_at=referencia,
            coverage_until=None,
            error_code=None,
        )
        self.assertEqual(status, IntegrationStatus.UNAVAILABLE)

    def test_thresholds_customizados_sao_respeitados(self):
        referencia = _AGORA - timedelta(seconds=100)
        status = calcular_status_integracao(
            heartbeat_at=_AGORA,
            last_success_at=referencia,
            coverage_until=None,
            error_code=None,
            limite_degradado_segundos=50,
            limite_indisponivel_segundos=200,
        )
        self.assertEqual(status, IntegrationStatus.DEGRADED)

    def test_limite_degradado_maior_que_indisponivel_levanta_value_error(self):
        with self.assertRaises(ValueError):
            calcular_status_integracao(
                heartbeat_at=_AGORA,
                last_success_at=_AGORA,
                coverage_until=None,
                error_code=None,
                limite_degradado_segundos=200,
                limite_indisponivel_segundos=100,
            )

    def test_limite_nao_positivo_levanta_value_error(self):
        with self.assertRaises(ValueError):
            calcular_status_integracao(
                heartbeat_at=_AGORA,
                last_success_at=_AGORA,
                coverage_until=None,
                error_code=None,
                limite_degradado_segundos=0,
                limite_indisponivel_segundos=100,
            )

    def test_error_code_vazio_levanta_value_error(self):
        with self.assertRaises(ValueError):
            calcular_status_integracao(
                heartbeat_at=_AGORA,
                last_success_at=_AGORA,
                coverage_until=None,
                error_code="   ",
            )

    def test_last_success_naive_e_rejeitado_mesmo_com_coverage_valido(self):
        with self.assertRaises(ValueError):
            calcular_status_integracao(
                heartbeat_at=_AGORA,
                last_success_at=_NAIVE,
                coverage_until=_AGORA - timedelta(seconds=10),
                error_code=None,
            )

    def test_last_success_no_futuro_rejeitado_mesmo_com_coverage_valido(self):
        with self.assertRaises(ValueError):
            calcular_status_integracao(
                heartbeat_at=_AGORA,
                last_success_at=_AGORA + timedelta(hours=1),
                coverage_until=_AGORA - timedelta(hours=1),
                error_code=None,
            )


class TestMontarSaudeIntegracao(unittest.TestCase):
    def test_registro_healthy_consistente(self):
        saude = montar_saude_integracao(
            integration="whatsapp",
            heartbeat_at=_AGORA,
            last_success_at=_AGORA - timedelta(seconds=30),
        )
        self.assertEqual(saude.status, IntegrationStatus.HEALTHY)
        self.assertEqual(saude.lag_seconds, 30.0)
        self.assertIsNone(saude.error_code)

    def test_registro_unknown_sem_nenhuma_leitura(self):
        saude = montar_saude_integracao(integration="sipac", heartbeat_at=_AGORA)
        self.assertEqual(saude.status, IntegrationStatus.UNKNOWN)
        self.assertIsNone(saude.lag_seconds)

    def test_registro_unavailable_por_erro(self):
        saude = montar_saude_integracao(
            integration="gmail",
            heartbeat_at=_AGORA,
            last_success_at=_AGORA,
            error_code="watch_expirado",
        )
        self.assertEqual(saude.status, IntegrationStatus.UNAVAILABLE)
        self.assertEqual(saude.error_code, "watch_expirado")

    def test_thresholds_customizados_produzem_registro_valido(self):
        saude = montar_saude_integracao(
            integration="drive",
            heartbeat_at=_AGORA,
            last_success_at=_AGORA - timedelta(seconds=100),
            limite_degradado_segundos=50,
            limite_indisponivel_segundos=200,
        )
        self.assertEqual(saude.status, IntegrationStatus.DEGRADED)

    def test_capabilities_default_vazio(self):
        saude = montar_saude_integracao(integration="drive", heartbeat_at=_AGORA)
        self.assertEqual(dict(saude.capabilities), {})

    def test_capabilities_preservadas(self):
        saude = montar_saude_integracao(
            integration="drive",
            heartbeat_at=_AGORA,
            capabilities={"leitura": True, "escrita": False},
        )
        self.assertEqual(dict(saude.capabilities), {"leitura": True, "escrita": False})

    def test_mutar_dict_de_capabilities_do_chamador_depois_nao_vaza(self):
        capabilities = {"leitura": True}
        saude = montar_saude_integracao(
            integration="drive", heartbeat_at=_AGORA, capabilities=capabilities
        )
        capabilities["leitura"] = False
        capabilities["nova"] = "x"
        self.assertEqual(dict(saude.capabilities), {"leitura": True})

    def test_mutar_dict_aninhado_de_capabilities_depois_nao_vaza(self):
        # Gap de cobertura apontado por revisão adversarial (P05 sub-entrega
        # 2/N): os testes anteriores só cobriam mutação de chave de topo --
        # uma regressão que trocasse o congelamento recursivo por uma cópia
        # RASA (`dict(self.capabilities)`) passaria despercebida sem este
        # teste, já que uma cópia rasa protege o dict de topo mas não o
        # dict aninhado dentro dele.
        capabilities = {"leitura": True, "detalhe": {"escopo": "completo"}}
        saude = montar_saude_integracao(
            integration="drive", heartbeat_at=_AGORA, capabilities=capabilities
        )
        capabilities["detalhe"]["escopo"] = "parcial"
        self.assertEqual(dict(saude.capabilities["detalhe"]), {"escopo": "completo"})
        with self.assertRaises(TypeError):
            saude.capabilities["detalhe"]["escopo"] = "parcial"


class TestIntegrationHealthPostInit(unittest.TestCase):
    def _valido(self, **overrides):
        base = dict(
            integration="whatsapp",
            heartbeat_at=_AGORA,
            status=IntegrationStatus.HEALTHY,
            last_success_at=_AGORA - timedelta(seconds=10),
            lag_seconds=10.0,
        )
        base.update(overrides)
        return base

    def test_construcao_direta_consistente_funciona(self):
        IntegrationHealth(**self._valido())

    def test_integration_vazio_levanta_value_error(self):
        with self.assertRaises(ValueError):
            IntegrationHealth(**self._valido(integration="   "))

    def test_error_code_vazio_levanta_value_error(self):
        with self.assertRaises(ValueError):
            IntegrationHealth(**self._valido(error_code="  "))

    def test_heartbeat_naive_levanta_value_error(self):
        with self.assertRaises(ValueError):
            IntegrationHealth(**self._valido(heartbeat_at=_NAIVE))

    def test_last_event_at_naive_levanta_value_error(self):
        with self.assertRaises(ValueError):
            IntegrationHealth(**self._valido(last_event_at=_NAIVE))

    def test_lag_seconds_incompativel_levanta_value_error(self):
        with self.assertRaises(ValueError):
            IntegrationHealth(**self._valido(lag_seconds=999.0))

    def test_status_healthy_sem_erro_mas_sem_leitura_levanta_value_error(self):
        with self.assertRaises(ValueError):
            IntegrationHealth(
                integration="whatsapp",
                heartbeat_at=_AGORA,
                status=IntegrationStatus.HEALTHY,
                lag_seconds=None,
            )

    def test_status_unavailable_sem_erro_e_sem_leitura_levanta_value_error(self):
        with self.assertRaises(ValueError):
            IntegrationHealth(
                integration="whatsapp",
                heartbeat_at=_AGORA,
                status=IntegrationStatus.UNAVAILABLE,
                lag_seconds=None,
            )

    def test_status_unknown_com_erro_presente_levanta_value_error(self):
        with self.assertRaises(ValueError):
            IntegrationHealth(
                integration="whatsapp",
                heartbeat_at=_AGORA,
                status=IntegrationStatus.UNKNOWN,
                last_success_at=_AGORA,
                lag_seconds=0.0,
                error_code="timeout",
            )

    def test_status_healthy_com_erro_presente_levanta_value_error(self):
        # Gap de cobertura apontado por revisão adversarial (P05 sub-entrega
        # 2/N): só havia teste de error_code + status errado para o caso
        # UNKNOWN; uma regressão que checasse só "error_code e status ==
        # UNKNOWN" (em vez de "error_code e status != UNAVAILABLE") passaria
        # despercebida sem este teste.
        with self.assertRaises(ValueError):
            IntegrationHealth(
                integration="whatsapp",
                heartbeat_at=_AGORA,
                status=IntegrationStatus.HEALTHY,
                last_success_at=_AGORA,
                lag_seconds=0.0,
                error_code="timeout",
            )

    def test_status_degraded_com_erro_presente_levanta_value_error(self):
        with self.assertRaises(ValueError):
            IntegrationHealth(
                integration="whatsapp",
                heartbeat_at=_AGORA,
                status=IntegrationStatus.DEGRADED,
                last_success_at=_AGORA - timedelta(seconds=100),
                lag_seconds=100.0,
                error_code="timeout",
            )

    def test_status_unknown_com_leitura_presente_levanta_value_error(self):
        with self.assertRaises(ValueError):
            IntegrationHealth(
                integration="whatsapp",
                heartbeat_at=_AGORA,
                status=IntegrationStatus.UNKNOWN,
                last_success_at=_AGORA,
                lag_seconds=0.0,
            )

    def test_status_degraded_com_threshold_customizado_eh_aceito_diretamente(self):
        # DEGRADED com lag de 100s não bateria com os thresholds DEFAULT (que
        # dariam HEALTHY), mas __post_init__ só exige consistência (uma das
        # 3 opções quando há leitura e nenhum erro), não igualdade a um
        # threshold fixo -- ver docstring da classe.
        IntegrationHealth(
            integration="whatsapp",
            heartbeat_at=_AGORA,
            status=IntegrationStatus.DEGRADED,
            last_success_at=_AGORA - timedelta(seconds=100),
            lag_seconds=100.0,
        )

    def test_registro_e_frozen(self):
        saude = IntegrationHealth(**self._valido())
        with self.assertRaises(Exception):
            saude.status = IntegrationStatus.UNAVAILABLE

    def test_capabilities_congeladas_recusam_mutacao_direta(self):
        saude = IntegrationHealth(**self._valido(capabilities={"leitura": True}))
        with self.assertRaises(TypeError):
            saude.capabilities["leitura"] = False


if __name__ == "__main__":
    unittest.main()
