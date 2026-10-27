import random
from zoneinfo import ZoneInfo
import unittest
from datetime import datetime, timedelta, timezone

from autonomy.requests import DEFAULT_MAX_TENTATIVAS, RequestStatus, validar_transicao
from autonomy.runner import ErroModelo, Esperar, ResultadoRunner, StatusRunner, TipoErroModelo
from autonomy.runner_continuacao import (
    MAX_PAUSAS_LIMITE, PAUSA_LIMITE_SEGUNDOS, decidir_continuacao,
)

AGORA = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def res(status, motivo="", **kw):
    return ResultadoRunner(status=status, motivo=motivo, **kw)


class DecidirContinuacaoTest(unittest.TestCase):
    def test_todas_as_saidas_sao_transicoes_validas_de_em_andamento(self):
        casos = [
            res(StatusRunner.CONCLUIDO), res(StatusRunner.AGUARDANDO, espera=Esperar("x")),
            res(StatusRunner.PAUSADO_LIMITE, "rodadas"), res(StatusRunner.RETENTAR, "rate_limit"),
            res(StatusRunner.FALHA, "recusa"),
        ]
        for r in casos:
            d = decidir_continuacao(r, AGORA)
            ok, motivo = validar_transicao(RequestStatus.EM_ANDAMENTO, d.novo_status)
            self.assertTrue(ok, (r.status, motivo))

    def test_concluido_vai_para_verificacao_nunca_concluido(self):
        d = decidir_continuacao(res(StatusRunner.CONCLUIDO, "ok"), AGORA)
        self.assertEqual(d.novo_status, RequestStatus.VERIFICANDO)
        self.assertIsNone(d.continuar_em)

    def test_aguardando_nao_agenda_continuacao_imediata(self):
        d = decidir_continuacao(res(StatusRunner.AGUARDANDO, espera=Esperar("resposta_do_andre")), AGORA)
        self.assertEqual(d.novo_status, RequestStatus.AGUARDANDO_EXTERNO)
        self.assertIsNone(d.continuar_em)
        self.assertEqual(d.condicao_espera, "resposta_do_andre")

    def test_aguardando_com_horario(self):
        quando = AGORA + timedelta(hours=3)
        d = decidir_continuacao(res(StatusRunner.AGUARDANDO, espera=Esperar("x", quando)), AGORA)
        self.assertEqual(d.continuar_em, quando)

    def test_aguardando_horario_sem_fuso_vira_sem_horario(self):
        d = decidir_continuacao(res(StatusRunner.AGUARDANDO, espera=Esperar("x", datetime(2026, 1, 1))), AGORA)
        self.assertIsNone(d.continuar_em)

    def test_pausa_por_limite_agenda_curto_sem_gastar_tentativa(self):
        d = decidir_continuacao(res(StatusRunner.PAUSADO_LIMITE, "tokens"), AGORA, tentativas=1, pausas=2)
        self.assertEqual(d.novo_status, RequestStatus.RETENTATIVA_AGENDADA)
        self.assertEqual(d.continuar_em, AGORA + timedelta(seconds=PAUSA_LIMITE_SEGUNDOS))
        self.assertEqual((d.tentativas, d.pausas), (1, 3))

    def test_pausas_esgotadas_viram_falha_final(self):
        d = decidir_continuacao(res(StatusRunner.PAUSADO_LIMITE, "rodadas"), AGORA, pausas=MAX_PAUSAS_LIMITE)
        self.assertEqual(d.novo_status, RequestStatus.FALHA_FINAL)
        self.assertEqual(d.motivo, "pausas_esgotadas")

    def test_retentar_usa_backoff_e_conta_tentativa(self):
        rng = random.Random(1)
        d = decidir_continuacao(res(StatusRunner.RETENTAR, "rate_limit"), AGORA, tentativas=0, rng=rng)
        self.assertEqual(d.novo_status, RequestStatus.RETENTATIVA_AGENDADA)
        self.assertEqual(d.tentativas, 1)
        delta = (d.continuar_em - AGORA).total_seconds()
        self.assertTrue(48 <= delta <= 72, delta)

    def test_retentar_esgota_apos_max_tentativas(self):
        d = decidir_continuacao(res(StatusRunner.RETENTAR, "timeout"), AGORA, tentativas=DEFAULT_MAX_TENTATIVAS)
        self.assertEqual(d.novo_status, RequestStatus.FALHA_FINAL)
        self.assertEqual(d.motivo, "tentativas_esgotadas")
        ult = decidir_continuacao(res(StatusRunner.RETENTAR), AGORA, tentativas=DEFAULT_MAX_TENTATIVAS - 1)
        self.assertEqual(ult.novo_status, RequestStatus.RETENTATIVA_AGENDADA)

    def test_falha_do_modelo_e_final(self):
        r = res(StatusRunner.FALHA, "recusa", erro_modelo=ErroModelo(TipoErroModelo.RECUSA))
        d = decidir_continuacao(r, AGORA, tentativas=1)
        self.assertEqual(d.novo_status, RequestStatus.FALHA_FINAL)
        self.assertEqual(d.motivo, "recusa")

    def test_soma_em_utc_com_fuso_de_dst(self):
        ag = datetime(2026, 11, 1, 1, 59, tzinfo=ZoneInfo("America/New_York"))
        d = decidir_continuacao(res(StatusRunner.PAUSADO_LIMITE, "x"), ag)
        self.assertEqual((d.continuar_em - ag).total_seconds(), PAUSA_LIMITE_SEGUNDOS)

    def test_agora_no_limite_do_calendario_e_value_error(self):
        with self.assertRaises(ValueError):
            decidir_continuacao(res(StatusRunner.PAUSADO_LIMITE), datetime.max.replace(tzinfo=timezone.utc))

    def test_aguardando_horario_de_tipo_errado_vira_sem_horario(self):
        for ruim in ("amanha", 123):
            d = decidir_continuacao(res(StatusRunner.AGUARDANDO, espera=Esperar("x", ruim)), AGORA)
            self.assertIsNone(d.continuar_em)

    def test_aguardando_horario_normalizado_para_utc(self):
        quando = datetime(2026, 10, 28, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
        d = decidir_continuacao(res(StatusRunner.AGUARDANDO, espera=Esperar("x", quando)), AGORA)
        self.assertEqual(d.continuar_em, quando)
        self.assertEqual(d.continuar_em.utcoffset(), timedelta(0))

    def test_normalizacao_no_limite_e_value_error(self):
        ag = datetime.min.replace(tzinfo=timezone(timedelta(hours=1)))
        with self.assertRaises(ValueError):
            decidir_continuacao(res(StatusRunner.CONCLUIDO), ag)

    def test_aguardando_sem_espera_falha_fechada(self):
        d = decidir_continuacao(res(StatusRunner.AGUARDANDO), AGORA)
        self.assertEqual((d.novo_status, d.motivo), (RequestStatus.FALHA_FINAL, "espera_sem_condicao"))

    def test_entrada_invalida_falha_fechada(self):
        self.assertEqual(decidir_continuacao("x", AGORA).novo_status, RequestStatus.FALHA_FINAL)
        self.assertEqual(
            decidir_continuacao(ResultadoRunner(status="concluido"), AGORA).novo_status,
            RequestStatus.FALHA_FINAL,
        )
        with self.assertRaises(ValueError):
            decidir_continuacao(res(StatusRunner.FALHA), datetime(2026, 1, 1))
        with self.assertRaises(ValueError):
            decidir_continuacao(res(StatusRunner.FALHA), AGORA, tentativas=-1)
        with self.assertRaises(ValueError):
            decidir_continuacao(res(StatusRunner.FALHA), AGORA, pausas=True)


if __name__ == "__main__":
    unittest.main()
