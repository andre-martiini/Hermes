"""Datas das parcelas (item 6), conciliacao fatura x conta (item 2) e custo de IA (item 14).

Casos reais: na fatura do Elo de 05/02/2026, compras de janeiro vieram como
2027; em out/2026 a XP somou R$ 200 de Google Cloud aos R$ 466,35 do Elo.
"""

import unittest

import fatura_cartao as fc
import historico_financeiro as hf
from test_importar_fatura import _Db


class TestAnoDaCompra(unittest.TestCase):
    def test_volta_o_ano_ate_antes_do_vencimento(self):
        self.assertEqual(fc.corrigir_ano_da_compra("2027-01-20", "2026-02-05"), "2026-01-20")
        self.assertEqual(fc.corrigir_ano_da_compra("2026-12-29", "2026-02-05"), "2025-12-29")

    def test_data_certa_fica(self):
        self.assertEqual(fc.corrigir_ano_da_compra("2026-01-20", "2026-02-05"), "2026-01-20")
        self.assertEqual(fc.corrigir_ano_da_compra("2026-02-05", "2026-02-05"), "2026-02-05")

    def test_sem_data_ou_formato_estranho(self):
        self.assertIsNone(fc.corrigir_ano_da_compra(None, "2026-02-05"))
        self.assertEqual(fc.corrigir_ano_da_compra("20/01", "2026-02-05"), "20/01")
        self.assertEqual(fc.corrigir_ano_da_compra("2027-01-20", None), "2027-01-20")

    def test_gravacao_ja_corrige(self):
        db = _Db()
        fc.salvar(db, "elo-caixa", {"cabecalho": {"total": 50.0, "vencimento": "2026-02-05"},
                                    "itens": [{"data": "2027-01-20", "estabelecimento": "GreenVix", "valor": 50.0}]})
        item = next(iter(db.banco[fc.COL_ITENS].values()))
        self.assertEqual(item["data"], "2026-01-20")

    def test_consulta_corrige_os_antigos_e_da_a_cobranca(self):
        db = _Db({
            fc.COL_FATURAS: {"elo-caixa-2026-02": {"cartao": "elo-caixa", "competencia": "2026-02",
                                                   "vencimento": "2026-02-05", "total": 50.0}},
            fc.COL_ITENS: {"a": {"tipo": "compra", "cartao": "elo-caixa", "fatura_id": "elo-caixa-2026-02",
                                 "competencia": "2026-02", "data": "2027-01-20", "estabelecimento": "GreenVix",
                                 "valor": 50.0}},
        })
        item = fc.consultar(db, competencia="2026-02")["lancamentos"][0]
        self.assertEqual((item["data_compra"], item["data_cobranca"]), ("2026-01-20", "2026-02-05"))


def _db_conciliacao(**conta):
    base = {"description": "Fatura Elo", "amount": 3814.14, "month": 9, "year": 2026, "isPaid": True}
    base.update(conta)
    return _Db({
        fc.COL_FATURAS: {
            "elo-caixa-2026-10": {"cartao": "elo-caixa", "competencia": "2026-10", "vencimento": "2026-10-05",
                                  "total": 3814.14},
            "xp-2026-10": {"cartao": "xp", "competencia": "2026-10", "vencimento": "2026-10-05", "total": 1315.98},
        },
        "fixed_bills": {"elo": base,
                        "copia": {"description": "Fatura Elo", "amount": 0, "month": 9, "year": 2026, "isPaid": False},
                        "fisio": {"description": "Elevar Fisio", "amount": 310, "month": 9, "year": 2026, "isPaid": True}},
    })


class TestConciliacao(unittest.TestCase):
    def _elo(self, db):
        return next(c for c in fc.conciliar(db, "2026-10") if c["cartao"] == "elo-caixa")

    def test_paga_fecha_em_zero(self):
        c = self._elo(_db_conciliacao())
        self.assertEqual((c["fatura_total"], c["pago"], c["saldo_em_aberto"]), (3814.14, 3814.14, 0.0))
        self.assertEqual(c["obrigacao"]["id"], "elo")  # a copia vazia nao conta
        self.assertEqual(c["diferenca_conta_x_fatura"], 0.0)

    def test_em_aberto(self):
        c = self._elo(_db_conciliacao(isPaid=False))
        self.assertEqual((c["pago"], c["saldo_em_aberto"]), (0.0, 3814.14))

    def test_pagamento_parcial_pelo_pix(self):
        c = self._elo(_db_conciliacao(valor_pago=3000.0))
        self.assertEqual((c["pago"], c["saldo_em_aberto"]), (3000.0, 814.14))

    def test_fatura_sem_conta_no_mes(self):
        xp = next(c for c in fc.conciliar(_db_conciliacao(), "2026-10") if c["cartao"] == "xp")
        self.assertIsNone(xp["obrigacao"])
        self.assertEqual(xp["saldo_em_aberto"], 1315.98)

    def test_consulta_traz_a_conciliacao_so_com_competencia(self):
        db = _db_conciliacao()
        self.assertEqual(len(fc.consultar(db, competencia="2026-10")["conciliacao"]), 2)
        self.assertIsNone(fc.consultar(db, desde="2026-01")["conciliacao"])


def _db_ia():
    itens = {
        "g1": ("DL GOOGLE CLOUD CGNF6", 466.35, "elo-caixa"),
        "g2": ("GOOGLE CLOUD NWBKZL", 100.0, "xp"),
        "g3": ("GOOGLE CLOUD 2XMFQB", 100.0, "xp"),
        "c1": ("ANTHROPIC* CLAUDE SUB", 901.09, "xp"),
        "t1": ("TYPESAFE AI, INC.", 53.53, "elo-caixa"),
        "u1": ("Uber UBER TRIP", 30.0, "elo-caixa"),
    }
    return _Db({fc.COL_ITENS: {
        k: {"tipo": "compra", "cartao": cartao, "fatura_id": f"{cartao}-2026-10", "competencia": "2026-10",
            "data": "2026-09-10", "estabelecimento": nome, "valor": valor}
        for k, (nome, valor, cartao) in itens.items()}})


class TestCustoIa(unittest.TestCase):
    def test_por_fornecedor_somando_os_cartoes(self):
        r = hf.custo_ia(_db_ia(), "2026-10")
        self.assertEqual(r["por_fornecedor"], {"Anthropic (Claude)": 901.09, "Google Cloud": 666.35,
                                               "Typesafe AI": 53.53})
        self.assertEqual(r["total"], 1620.97)

    def test_meta_do_google_cloud(self):
        r = hf.custo_ia(_db_ia(), "2026-10")["google_cloud"]
        self.assertEqual((r["valor"], r["meta"], r["acima_da_meta"]), (666.35, 100.0, True))
        vazio = hf.custo_ia(_Db(), "2026-10")
        self.assertEqual((vazio["total"], vazio["google_cloud"]["acima_da_meta"]), (0.0, False))

    def test_entra_no_retrato_e_no_comparativo(self):
        from datetime import date

        db = _db_ia()
        self.assertEqual(hf.montar_mes(db, "2026-10")["custo_ia"]["total"], 1620.97)
        linha = hf.consultar(db, "2026-10", "2026-10", hoje=date(2026, 10, 13))["comparativo"][0]
        self.assertEqual(linha["custo_ia"], 1620.97)


if __name__ == "__main__":
    unittest.main()
