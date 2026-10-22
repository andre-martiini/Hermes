import unittest
from datetime import datetime, timezone, timedelta

from autonomy.atencao_compromisso import (
    deve_gravar, id_item_atencao, marcar_enviado, montar_item_atencao, proxima_avaliacao,
)
from autonomy.followup_guard import ADIAR, ENVIAR, SUPRIMIR, DecisaoFollowup

AGORA = datetime(2026, 10, 22, 12, 0, 30, 999, tzinfo=timezone(timedelta(hours=-3)))
CH = "chat1__m1__0"


class AtencaoCompromissoTest(unittest.TestCase):
    def test_id_por_chave_e_versao(self):
        self.assertEqual(id_item_atencao(CH, 2), CH + "__v2")
        for v in (0, -1, True, "1", None):
            with self.assertRaises(ValueError):
                id_item_atencao(CH, v)
        for c in ("", " x", None):
            with self.assertRaises(ValueError):
                id_item_atencao(c, 1)

    def test_proxima_avaliacao(self):
        self.assertEqual(proxima_avaliacao(DecisaoFollowup(ENVIAR, "ok"), AGORA).hour, 15)
        self.assertEqual(proxima_avaliacao(DecisaoFollowup(ADIAR, "x"), AGORA).hour, 19)
        self.assertIsNone(proxima_avaliacao(DecisaoFollowup(SUPRIMIR, "x"), AGORA))
        with self.assertRaises(ValueError):
            proxima_avaliacao(DecisaoFollowup("outro", "x"), AGORA)
        with self.assertRaises(ValueError):
            proxima_avaliacao(DecisaoFollowup(ENVIAR, "x"), datetime(2026, 1, 1))

    def test_montar(self):
        it = montar_item_atencao(CH, 1, DecisaoFollowup(SUPRIMIR, "cumprido"), AGORA)
        self.assertEqual(it["estado"], "encerrado")
        self.assertIsNone(it["proxima_avaliacao"])
        self.assertEqual(it["avaliado_em"], "2026-10-22T15:00:30+00:00")
        it = montar_item_atencao(CH, 1, DecisaoFollowup(ADIAR, "d"), AGORA)
        self.assertEqual(it["estado"], "aberto")
        self.assertEqual(it["proxima_avaliacao"], "2026-10-22T19:00:30+00:00")

    def test_deve_gravar(self):
        a = montar_item_atencao(CH, 1, DecisaoFollowup(ADIAR, "d"), AGORA)
        self.assertTrue(deve_gravar(None, a))
        self.assertFalse(deve_gravar(a, a))
        b = montar_item_atencao(CH, 1, DecisaoFollowup(ENVIAR, "ok"), AGORA)
        self.assertTrue(deve_gravar(a, b))
        enc = montar_item_atencao(CH, 1, DecisaoFollowup(SUPRIMIR, "c"), AGORA)
        self.assertFalse(deve_gravar(enc, b))
        v2 = montar_item_atencao(CH, 2, DecisaoFollowup(ADIAR, "d"), AGORA)
        self.assertTrue(deve_gravar(b, v2))
        self.assertFalse(deve_gravar(v2, b))
        outro = montar_item_atencao("c2__m__0", 1, DecisaoFollowup(ADIAR, "d"), AGORA)
        self.assertFalse(deve_gravar(a, outro))
        self.assertFalse(deve_gravar({"x": 1}, a))

    def test_renova_agendamento_e_ordem_temporal(self):
        mais_tarde = AGORA + timedelta(hours=5)
        a = montar_item_atencao(CH, 1, DecisaoFollowup(ADIAR, "d"), AGORA)
        b = montar_item_atencao(CH, 1, DecisaoFollowup(ADIAR, "d"), mais_tarde)
        self.assertTrue(deve_gravar(a, b))
        self.assertFalse(deve_gravar(b, a))
        velho = montar_item_atencao(CH, 1, DecisaoFollowup(ENVIAR, "ok"), AGORA - timedelta(hours=1))
        self.assertFalse(deve_gravar(a, velho))

    def test_enviado_e_terminal(self):
        e = montar_item_atencao(CH, 1, DecisaoFollowup(ENVIAR, "ok"), AGORA)
        env = marcar_enviado(e, AGORA)
        self.assertEqual(env["estado"], "enviado")
        self.assertFalse(deve_gravar(env, montar_item_atencao(CH, 1, DecisaoFollowup(ENVIAR, "ok"), AGORA + timedelta(hours=9))))

    def test_malformados(self):
        a = montar_item_atencao(CH, 1, DecisaoFollowup(ADIAR, "d"), AGORA)
        b = montar_item_atencao(CH, 1, DecisaoFollowup(ADIAR, "d"), AGORA + timedelta(hours=5))
        for ruim in ({**a, "estado": "xx"}, {**a, "versao": True}, {**a, "id": "outro"}):
            self.assertFalse(deve_gravar(ruim, b))
        self.assertFalse(deve_gravar(a, {**b, "estado": "xx"}))
        with self.assertRaises(ValueError):
            montar_item_atencao(CH, 1, None, AGORA)
        with self.assertRaises(ValueError):
            montar_item_atencao("a/b", 1, DecisaoFollowup(ADIAR, "d"), AGORA)
        with self.assertRaises(ValueError):
            montar_item_atencao("a b", 1, DecisaoFollowup(ADIAR, "d"), AGORA)
        with self.assertRaises(ValueError):
            montar_item_atencao(CH, 1, DecisaoFollowup(ADIAR, "d"), datetime.max.replace(tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
