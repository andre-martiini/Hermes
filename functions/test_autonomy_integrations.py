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
