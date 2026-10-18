"""Fonte de cada renda: o salario do Ifes e reconhecido pelo nome, nao pela categoria.

Casos reais de 2026: em fev, "Renda Principal" tinha a Remuneracao IFES e
tambem Diarias Facto e o servico do Reforco Positivo; em mar o salario veio
como "Ifes Remuneracao" na categoria "Renda principal" (minuscula); em jun,
reembolso do ChatGPT e restituicao do IRPF.
"""

import unittest

import fontes_renda as fr
import historico_financeiro as hf
from test_importar_fatura import _Db


class TestFonte(unittest.TestCase):
    def test_salario_pelo_nome(self):
        for nome in ("Remuneração IFES", "Ifes Remuneração", "REMUNERACAO IFES"):
            self.assertTrue(fr.e_salario_ifes({"description": nome}), nome)

    def test_mesma_categoria_nao_e_salario(self):
        for nome in ("Diárias Facto", "Serviço Reforço Positivo", "Reembolso ChatGPT", "Restituição IRPF 2026"):
            r = {"description": nome, "category": "Renda Principal"}
            self.assertEqual(fr.fonte(r), "outras", nome)

    def test_servicos_sem_diferenciar_maiusculas(self):
        self.assertEqual(fr.fonte({"description": "Bolsa Sigex", "category": "Bolsa"}), "servicos")
        self.assertEqual(fr.fonte({"description": "PLS MEC", "category": "serviço particular"}), "servicos")


class TestHistoricoPorFonte(unittest.TestCase):
    def test_fevereiro_real(self):
        db = _Db({"income_entries": {
            "a": {"description": "Remuneração IFES", "category": "Renda Principal", "amount": 8344.66,
                  "month": 1, "year": 2026},
            "b": {"description": "Diárias Facto", "category": "Renda Principal", "amount": 980,
                  "month": 1, "year": 2026},
            "c": {"description": "Bolsa Sigex", "category": "Bolsa", "amount": 4500, "month": 1, "year": 2026},
            "d": {"description": "Serviço Reforço Positivo", "category": "Renda Principal", "amount": 1000,
                  "month": 1, "year": 2026},
        }, "finance_settings": {"config": {}}})
        self.assertEqual(hf.montar_mes(db, "2026-02")["renda"]["por_fonte"],
                         {"ifes": 8344.66, "servicos": 4500.0, "outras": 1980.0})


if __name__ == "__main__":
    unittest.main()
