"""Contracheque do Ifes por rubrica (item 13).

Valores do contracheque real de JAN/2026: bruto 10.368,11, desconto 2.023,45,
liquido 8.344,66, per capita de saude suplementar 542,24.
"""

import unittest
from unittest import mock

import contracheque as cq
import historico_financeiro as hf
from test_importar_fatura import _Db

JAN_2026 = {
    "mes_ano": "JAN 2026",
    "rendimentos": [
        {"descricao": "VENCIMENTO BASICO", "valor": 5372.35},
        {"descricao": "AUXÍLIO-ALIMENTACÃO", "valor": "1.175,00"},
        {"descricao": "ASSISTENCIA PRE-ESCOLAR", "valor": 484.90},
        {"descricao": "PER CAPITA - SAUDE SUPLEMENTAR", "valor": 542.24},
        {"descricao": "IQ - 52% - LEI 11.091/05 AT", "valor": 2793.62},
    ],
    "descontos": [
        {"descricao": "MENSALIDADE SINDICAL - SINASEF", "valor": 81.65},
        {"descricao": "COTA PARTE PRE-ESCOLAR", "valor": -24.24},
        {"descricao": "CONT. PLANO SEGURIDADE SOCIAL", "valor": 944.73},
        {"descricao": "IMPOSTO DE RENDA RETIDO FONTE", "valor": 972.83},
    ],
    "bruto": 10368.11, "desconto": 2023.45, "liquido": 8344.66,
}


class TestLeitura(unittest.TestCase):
    def test_mes_ano(self):
        self.assertEqual(cq.competencia_do_mes_ano("JAN 2026"), "2026-01")
        self.assertEqual(cq.competencia_do_mes_ano("out/2025"), "2025-10")
        with self.assertRaises(ValueError):
            cq.competencia_do_mes_ano("13 2026")

    def test_janeiro_confere(self):
        r = cq.normalizar(JAN_2026)
        self.assertEqual(r["competencia"], "2026-01")
        self.assertTrue(r["confere"])
        self.assertEqual(r["per_capita_saude"], 542.24)
        self.assertEqual(r["descontos"][1]["valor"], 24.24)  # sinal tirado
        self.assertEqual(r["rendimentos"][1]["valor"], 1175.0)  # "1.175,00"

    def test_soma_que_nao_bate_e_apontada(self):
        r = cq.normalizar(dict(JAN_2026, bruto=10000.0))
        self.assertFalse(r["confere"])
        self.assertIn("bruto impresso", " ".join(r["divergencias"]))

    def test_nao_guarda_dado_pessoal(self):
        com_pii = dict(JAN_2026, nome="FULANO", cpf="000.000.000-00", conta="0000252681", siape="2921016")
        r = cq.normalizar(com_pii)
        self.assertEqual(set(r), {"competencia", "rendimentos", "descontos", "bruto", "desconto", "liquido",
                                  "per_capita_saude", "confere", "divergencias"})
        self.assertNotIn("000.000.000-00", str(r))
        self.assertNotIn("CPF", cq._PROMPT.split("NÃO transcreva")[0])


def _db():
    return _Db({
        "income_entries": {
            "fev": {"description": "Remuneração IFES", "amount": 8344.66, "month": 1, "year": 2026,
                    "category": "Renda Principal"},
            # Mesma categoria, mas nao e salario (caso real de fev/2026).
            "diarias": {"description": "Diárias Facto", "amount": 980, "month": 1, "year": 2026,
                        "category": "Renda Principal"},
            "excluida": {"description": "Remuneração IFES", "amount": 999, "month": 1, "year": 2026,
                         "category": "Renda Principal", "status": "deleted"},
        },
        "fixed_bills": {
            "plano": {"description": "Allcare plano de saúde", "amount": 3069.76, "month": 0, "year": 2026},
            "copart": {"description": "ALLCARE (COPARTICIPAÇÃO)", "amount": 493.92, "month": 0, "year": 2026},
            "luz": {"description": "EDP", "amount": 300, "month": 0, "year": 2026},
        },
        "finance_settings": {"config": {}},
    })


class TestGravacao(unittest.TestCase):
    def test_grava_rele_e_compara_com_a_renda_do_mes_seguinte(self):
        db = _db()
        r = cq.gravar(db, cq.normalizar(JAN_2026), origem={"arquivo": "contracheque_1_2026.pdf"})
        self.assertEqual((r["estado"], r["liquido"], r["per_capita_saude"]), ("verificado", 8344.66, 542.24))
        self.assertEqual(r["renda_lancada"], {"mes": "2026-02", "valor": 8344.66, "diferenca_para_o_liquido": 0.0})
        self.assertEqual(db.banco["contracheques"]["2026-01"]["arquivo"], "contracheque_1_2026.pdf")

    def test_dezembro_compara_com_janeiro_do_ano_seguinte(self):
        self.assertEqual(cq.renda_lancada(_Db(), "2025-12"), (None, "2026-01"))

    def test_saude_liquida(self):
        db = _db()
        self.assertIsNone(cq.saude_liquida(db, "2026-01"))
        cq.gravar(db, cq.normalizar(JAN_2026))
        self.assertEqual(cq.saude_liquida(db, "2026-01"),
                         {"plano_e_coparticipacao": 3563.68, "per_capita": 542.24, "custo_liquido": 3021.44})

    def test_entra_no_historico(self):
        db = _db()
        cq.gravar(db, cq.normalizar(JAN_2026))
        r = hf.montar_mes(db, "2026-01")
        self.assertEqual(r["contracheque"]["liquido"], 8344.66)
        self.assertEqual(r["saude"]["custo_liquido"], 3021.44)
        self.assertIsNone(hf.montar_mes(db, "2026-02")["contracheque"])


class TestFerramenta(unittest.TestCase):
    def _chamar(self, dados, nome="contracheque_1_2026.pdf"):
        from tools import hermes_tools

        ctx = mock.Mock()
        ctx.db = _db()
        with mock.patch("tools.anexar_arquivo._do_drive", return_value=(dados, nome)), \
             mock.patch.object(cq, "extrair", return_value=JAN_2026):
            return hermes_tools.importar_contracheque(ctx, {"drive_file_id": "abc"})

    def test_sucesso(self):
        r = self._chamar(b"%PDF-1.4 ...")
        self.assertEqual((r["estado"], r["competencia"]), ("verificado", "2026-01"))

    def test_nao_pdf(self):
        self.assertIn("nao e PDF", self._chamar(b"ola", "nota.txt")["erro"])

    def test_falha_de_releitura_vira_erro(self):
        with mock.patch.object(cq, "gravar", return_value={"estado": "falhou", "motivo": "x"}):
            r = self._chamar(b"%PDF-1.4 ...")
        self.assertIn("nao confirmado", r["erro"])


if __name__ == "__main__":
    unittest.main()
