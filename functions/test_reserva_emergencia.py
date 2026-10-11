"""Reserva de emergencia editavel pela tool `atualizar_reserva_emergencia`.

Caso real: em 02/10/2026 a XP mostrava R$ 25.780,07 no Pos-Fixado e o Gaspar
R$ 26.451,50, sem tool que corrigisse.
"""

import unittest
from unittest import mock

import reserva_emergencia as re_
from test_importar_fatura import _Db


def _db(**config):
    base = {"emergencyReserveCurrent": 26451.5, "emergencyReserveTarget": 25000,
            "monthlyBudget": 5000, "investmentReserveCurrent": 1617.27}
    base.update(config)
    return _Db({"finance_settings": {"config": base}})


class TestAtualizar(unittest.TestCase):
    def test_corrige_o_valor_atual_e_relê(self):
        db = _db()
        r = re_.atualizar(db, valor_atual=25780.07, fonte="XP, Pós-Fixado, 02/10")
        self.assertEqual(r["estado"], "verificado")
        self.assertEqual(r["reserva"], {"atual": 25780.07, "alvo": 25000})
        self.assertEqual(r["anterior"]["atual"], 26451.5)

    def test_so_mexe_nos_campos_da_reserva(self):
        db = _db()
        re_.atualizar(db, valor_atual=25780.07)
        config = db.banco["finance_settings"]["config"]
        self.assertEqual((config["monthlyBudget"], config["investmentReserveCurrent"]), (5000, 1617.27))

    def test_registra_historico_com_a_fonte(self):
        db = _db()
        r = re_.atualizar(db, valor_atual=25780.07, fonte="XP")
        hist = db.banco[re_.COLECAO_HISTORICO][r["historico_id"]]
        self.assertEqual(hist["mudancas"], {"emergencyReserveCurrent": {"de": 26451.5, "para": 25780.07}})
        self.assertEqual(hist["fonte"], "XP")

    def test_mesmo_valor_nao_grava_nem_registra(self):
        db = _db()
        r = re_.atualizar(db, valor_atual=26451.50)
        self.assertTrue(r["sem_mudanca"])
        self.assertNotIn(re_.COLECAO_HISTORICO, db.banco)

    def test_alvo_sozinho(self):
        r = re_.atualizar(_db(), valor_alvo=30000)
        self.assertEqual(r["reserva"], {"atual": 26451.5, "alvo": 30000})

    def test_valor_em_texto_brasileiro(self):
        r = re_.atualizar(_db(), valor_atual="R$ 25.780,07")
        self.assertEqual(r["reserva"]["atual"], 25780.07)

    def test_validacoes(self):
        with self.assertRaisesRegex(ValueError, "Informe"):
            re_.atualizar(_db())
        with self.assertRaisesRegex(ValueError, "faixa"):
            re_.atualizar(_db(), valor_atual=-1)
        with self.assertRaisesRegex(ValueError, "nao e um valor"):
            re_.atualizar(_db(), valor_atual="muito")
        with self.assertRaisesRegex(ValueError, "valor em reais"):
            re_.atualizar(_db(), valor_atual=True)

    def test_releitura_que_nao_bate_e_falha(self):
        db = _db()
        original = db.collection

        def colecao(nome):
            consulta = original(nome)
            if nome != re_.COLECAO_CONFIG:
                return consulta
            ref = consulta.document(re_.DOC_CONFIG)
            ref_set = ref.set
            ref.set = lambda dados, merge=False: ref_set({k: 0 for k in dados}, merge=merge)
            consulta.document = lambda _id: ref
            return consulta

        db.collection = colecao
        r = re_.atualizar(db, valor_atual=25780.07)
        self.assertEqual(r["estado"], "falhou")


class TestFerramenta(unittest.TestCase):
    def _chamar(self, db, **args):
        from tools import hermes_tools

        ctx = mock.Mock()
        ctx.db = db
        return hermes_tools.atualizar_reserva_emergencia(ctx, args)

    def test_sucesso(self):
        r = self._chamar(_db(), valor_atual=25780.07, fonte="XP")
        self.assertEqual((r["estado"], r["reserva"]["atual"]), ("verificado", 25780.07))

    def test_erro_vira_mensagem(self):
        self.assertIn("Informe", self._chamar(_db())["erro"])

    def test_falha_vira_erro(self):
        with mock.patch.object(re_, "atualizar", return_value={"estado": "falhou", "motivo": "x"}):
            self.assertIn("nao confirmada", self._chamar(_db(), valor_atual=1)["erro"])


if __name__ == "__main__":
    unittest.main()
