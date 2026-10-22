import unittest
from datetime import date, datetime, timedelta, timezone

from autonomy import prazo_followup as pf
from autonomy.commitments import PRAZO_ESTIMADO, PRAZO_EXPRESSO, Prazo

from datetime import tzinfo


class _Explode(list):
    def __iter__(self):
        raise RuntimeError("x")


class _NaturezaHostil:
    def __eq__(self, o):
        raise RuntimeError("x")


class _TzHostil(tzinfo):
    def utcoffset(self, d):
        raise RuntimeError("boom")


BASE = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


class PrazoFollowupTest(unittest.TestCase):
    def test_prazo_expresso_com_data_e_vinculante_e_vence_no_fim_do_dia(self):
        a = pf.planejar_acompanhamento(Prazo(PRAZO_EXPRESSO, "amanhã", date(2026, 10, 23)), BASE)
        self.assertTrue(a.vinculante)
        self.assertEqual(a.origem, pf.ORIGEM_EXPRESSO)
        # 23/10 23:59:59 em São Paulo (-03) + 1s = 24/10 03:00 UTC
        self.assertEqual(a.verificar_em, datetime(2026, 10, 24, 3, 0, tzinfo=timezone.utc))

    def test_prazo_expresso_nao_e_antecipado_pelo_historico(self):
        a = pf.planejar_acompanhamento(
            Prazo(PRAZO_EXPRESSO, "sexta", date(2026, 10, 30)), BASE, [1, 1, 1, 1, 1, 1])
        self.assertEqual(a.origem, pf.ORIGEM_EXPRESSO)
        self.assertGreater(a.verificar_em, BASE + timedelta(days=7))

    def test_sem_amostra_minima_usa_padrao_nao_vinculante(self):
        a = pf.planejar_acompanhamento(None, BASE, [2, 3, 4, 5])
        self.assertEqual(a.origem, pf.ORIGEM_PADRAO)
        self.assertFalse(a.vinculante)
        self.assertEqual(a.verificar_em, BASE + timedelta(hours=24))

    def test_historico_suficiente_usa_p75_nao_vinculante(self):
        a = pf.planejar_acompanhamento(None, BASE, [1, 2, 3, 4, 40])
        self.assertEqual(a.origem, pf.ORIGEM_HISTORICO)
        self.assertFalse(a.vinculante)
        self.assertEqual(a.amostra, 5)
        self.assertEqual(a.verificar_em, BASE + timedelta(hours=4))

    def test_estimativa_limitada(self):
        self.assertEqual(pf.estimar_horas([0.1] * 5), 1.0)
        self.assertEqual(pf.estimar_horas([1000] * 5), 168.0)

    def test_prazo_estimado_ou_sem_data_nao_e_vinculante(self):
        for p in (Prazo(PRAZO_ESTIMADO, "em breve"), Prazo(PRAZO_EXPRESSO, "hoje")):
            a = pf.planejar_acompanhamento(p, BASE)
            self.assertFalse(a.vinculante)
            self.assertEqual(a.origem, pf.ORIGEM_PADRAO)

    def test_sem_microssegundos_e_fim_do_dia_em_fuso_com_hora_repetida(self):
        a = pf.planejar_acompanhamento(None, BASE, [1.0000001] * 5)
        self.assertEqual(a.verificar_em.microsecond, 0)
        # 17/02/2018 em São Paulo ainda tinha a hora 23h repetida (fim do horário de verão)
        b = pf.planejar_acompanhamento(
            Prazo(PRAZO_EXPRESSO, "x", date(2018, 2, 17)), datetime(2018, 2, 10, tzinfo=timezone.utc))
        self.assertEqual(b.verificar_em, datetime(2018, 2, 18, 3, 0, tzinfo=timezone.utc))

    def test_data_do_prazo_deve_ser_date_puro(self):
        with self.assertRaises(ValueError):
            pf.planejar_acompanhamento(Prazo(PRAZO_EXPRESSO, "x", datetime(2026, 10, 25)), BASE)

    def test_int_enorme_vira_limite_e_nao_estoura(self):
        self.assertEqual(pf.estimar_horas([10**400] * 5), 168.0)

    def test_entradas_ruins_viram_value_error(self):
        ruins = [
            lambda: pf.planejar_acompanhamento("amanhã", BASE),
            lambda: pf.planejar_acompanhamento(None, datetime(2026, 1, 1)),
            lambda: pf.planejar_acompanhamento(None, BASE, [True] * 5),
            lambda: pf.planejar_acompanhamento(None, BASE, [float("nan")] * 5),
            lambda: pf.planejar_acompanhamento(None, BASE, [-1] * 5),
            lambda: pf.planejar_acompanhamento(None, BASE, "12345"),
            lambda: pf.planejar_acompanhamento(None, BASE, fuso="Marte/Olimpo"),
            lambda: pf.planejar_acompanhamento(Prazo(PRAZO_EXPRESSO, "ontem", date(2026, 10, 21)), BASE),
            lambda: pf.planejar_acompanhamento(Prazo(PRAZO_EXPRESSO, "x", date(9999, 12, 31)), BASE),
            lambda: pf.planejar_acompanhamento(None, datetime.max.replace(tzinfo=timezone.utc)),
            lambda: pf.estimar_horas([1] * 5, amostra_minima=0),
            lambda: pf.estimar_horas(bytearray(b"\x02" * 5)),
            lambda: pf.planejar_acompanhamento(Prazo(PRAZO_EXPRESSO, "x", "2026-10-25"), BASE),
            lambda: pf.planejar_acompanhamento(Prazo("lixo", "x", date(2026, 10, 25)), BASE),
            lambda: pf.planejar_acompanhamento(None, BASE, (h for h in [1.0])),
            lambda: pf.planejar_acompanhamento(None, BASE, _Explode()),
            lambda: pf.planejar_acompanhamento(Prazo(_NaturezaHostil(), "x", None), BASE),
            lambda: pf.planejar_acompanhamento(None, datetime(2026, 1, 1, tzinfo=_TzHostil())),
        ]
        for i, f in enumerate(ruins):
            with self.subTest(i=i):
                with self.assertRaises(ValueError):
                    f()


if __name__ == "__main__":
    unittest.main()
