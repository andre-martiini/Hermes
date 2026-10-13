"""Historico mensal do financeiro (item 4) e mes por competencia "YYYY-MM" (item 5).

Os valores sao os de setembro/2026 depois da correcao de 11/10 (saldo R$ 5.136,75).
"""

import json
import unittest
from datetime import date, datetime
from unittest import mock

import competencia as comp
import fatura_cartao
import historico_financeiro as hf
from test_importar_fatura import _Db

HOJE = date(2026, 10, 12)


def _db_setembro():
    return _Db({
        "fixed_bills": {
            "elo": {"description": "Fatura Elo", "amount": 5721.28, "month": 8, "year": 2026, "isPaid": True},
            "agua": {"description": "Cesan", "amount": 303.27, "month": 8, "year": 2026, "isPaid": False},
            "poup": {"description": "Poupança", "amount": 500, "month": 8, "year": 2026, "isPaid": True,
                     "category": "Poupança"},
            "out": {"description": "Fatura Elo", "amount": 3814.14, "month": 9, "year": 2026, "isPaid": True},
        },
        "income_entries": {
            "ifes": {"amount": 9096.95, "month": 8, "year": 2026, "status": "active", "isReceived": True,
                     "category": "Renda Principal"},
            "sigex": {"amount": 4500, "month": 8, "year": 2026, "status": "active", "isReceived": True,
                      "category": "Serviço Particular"},
            "apagada": {"amount": 4500, "month": 8, "year": 2026, "status": "deleted", "isReceived": True,
                        "category": "Serviço Particular"},
            "venda": {"amount": 100, "month": 8, "year": 2026, "status": "active", "isReceived": False},
        },
        fatura_cartao.COL_ITENS: {
            "a": {"tipo": "compra", "cartao": "elo-caixa", "fatura_id": "elo-caixa-2026-09", "competencia": "2026-09",
                  "data": "2026-08-10", "estabelecimento": "Uber UBER TRIP", "valor": 40.0},
            "b": {"tipo": "compra", "cartao": "elo-caixa", "fatura_id": "elo-caixa-2026-09", "competencia": "2026-09",
                  "data": "2026-08-12", "estabelecimento": "SUPERMERCADO PERIM", "valor": 300.0},
        },
        "finance_settings": {"config": {"emergencyReserveCurrent": 25780.07, "emergencyReserveTarget": 25000}},
        "finance_goals": {"g": {"name": "Ar-condicionado", "targetAmount": 2900, "status": "queued"}},
    })


class TestCompetencia(unittest.TestCase):
    def test_ler_e_periodo(self):
        self.assertEqual(comp.ler("2026-10"), (9, 2026))
        self.assertEqual(comp.periodo(8, 2026), {"mes": 8, "ano": 2026, "competencia": "2026-09",
                                                 "mes_nome": "setembro", "mes_1a12": 9})

    def test_competencia_vence_mes(self):
        self.assertEqual(comp.resolver({"competencia": "2026-09", "mes": 2, "ano": 2020}), (8, 2026))

    def test_mes_0_a_11_continua_valendo(self):
        self.assertEqual(comp.resolver({"mes": 8, "ano": 2026}), (8, 2026))
        self.assertEqual(comp.resolver({}, datetime(2026, 10, 12)), (9, 2026))

    def test_formato_invalido(self):
        for ruim in ("2026-13", "10/2026", "2026-1", "out"):
            with self.assertRaises(ValueError, msg=ruim):
                comp.ler(ruim)


class TestToolsFinanceirasComCompetencia(unittest.TestCase):
    def test_consulta_devolve_o_nome_do_mes(self):
        from tools import telegram_extended

        r = json.loads(telegram_extended.execute("consultar_financas_v2", {"competencia": "2026-09"},
                                                 db=_db_setembro()))
        self.assertEqual((r["periodo"]["competencia"], r["periodo"]["mes_nome"]), ("2026-09", "setembro"))
        self.assertAlmostEqual(r["resumo"]["total_contas"], 6524.55, places=2)

    def test_consulta_com_competencia_invalida(self):
        from tools import telegram_extended

        r = telegram_extended.execute("consultar_financas_v2", {"competencia": "set/2026"}, db=_Db())
        self.assertTrue(r.startswith("ERRO|"))

    def test_registro_usa_a_competencia(self):
        from tools import telegram_extended

        db = _Db()
        r = json.loads(telegram_extended.execute(
            "registrar_item_financeiro_v2",
            {"tipo": "renda", "descricao": "Venda", "valor": 50, "competencia": "2026-11"}, db=db))
        self.assertTrue(r["success"])
        gravado = next(iter(db.banco["income_entries"].values()))
        self.assertEqual((gravado["month"], gravado["year"]), (10, 2026))


class TestRetratoDoMes(unittest.TestCase):
    def test_setembro(self):
        r = hf.montar_mes(_db_setembro(), "2026-09")
        self.assertEqual(r["periodo"]["mes_nome"], "setembro")
        self.assertEqual(r["renda"], {"total": 13696.95, "recebida": 13596.95,
                                      "por_fonte": {"ifes": 9096.95, "servicos": 4500.0, "outras": 100.0}})
        self.assertEqual(r["contas"], {"total": 6524.55, "pagas": 6221.28, "quantidade": 3, "aportes": 500.0})
        self.assertEqual(r["saldo"], {"previsto": 7172.4, "realizado": 7375.67})
        self.assertEqual(r["cartao"]["total_gasto"], 340.0)
        self.assertEqual({c["categoria"] for c in r["cartao"]["por_categoria"]}, {"Transporte", "Mercado"})
        self.assertEqual(r["reserva_emergencia"]["atual"], 25780.07)


class TestFechamento(unittest.TestCase):
    def test_fecha_congela_e_nao_refaz_sozinho(self):
        db = _db_setembro()
        r = hf.fechar_mes(db, "2026-09", hoje=HOJE)
        self.assertEqual((r["estado"], r["versao"]), ("verificado", 1))
        db.banco["fixed_bills"]["agua"]["amount"] = 999.0
        self.assertEqual(hf.fechar_mes(db, "2026-09", hoje=HOJE)["estado"], "ja_fechado")
        congelado = hf.consultar(db, "2026-09", "2026-09", hoje=HOJE)["meses"][0]
        self.assertEqual((congelado["situacao"], congelado["contas"]["total"]), ("fechado", 6524.55))

    def test_retificar_exige_motivo_e_guarda_a_versao_anterior(self):
        db = _db_setembro()
        hf.fechar_mes(db, "2026-09", hoje=HOJE)
        db.banco["fixed_bills"]["agua"]["amount"] = 999.0
        with self.assertRaisesRegex(ValueError, "motivo"):
            hf.fechar_mes(db, "2026-09", hoje=HOJE, retificar=True)
        r = hf.fechar_mes(db, "2026-09", hoje=HOJE, retificar=True, motivo="conta da Cesan corrigida")
        self.assertEqual(r["versao"], 2)
        retrato = db.banco[hf.COLECAO]["2026-09"]
        self.assertEqual(retrato["retificacoes"][0]["anterior"]["contas"], 6524.55)
        self.assertEqual(retrato["contas"]["total"], 7220.28)

    def test_nao_fecha_mes_em_curso(self):
        with self.assertRaisesRegex(ValueError, "nao terminou"):
            hf.fechar_mes(_db_setembro(), "2026-10", hoje=HOJE)
        with self.assertRaisesRegex(ValueError, "nao terminou"):
            hf.fechar_mes(_db_setembro(), "2026-12", hoje=HOJE)

    def test_releitura_que_nao_bate_e_falha(self):
        db = _db_setembro()
        original = db.collection

        def colecao(nome):
            consulta = original(nome)
            if nome != hf.COLECAO:
                return consulta
            ref = consulta.document("2026-09")
            ref.get = lambda: type("S", (), {"to_dict": lambda self: None, "exists": False})()
            consulta.document = lambda _id: ref
            return consulta

        db.collection = colecao
        self.assertEqual(hf.fechar_mes(db, "2026-09", hoje=HOJE)["estado"], "falhou")


class TestConsulta(unittest.TestCase):
    def test_doze_meses_numa_chamada(self):
        r = hf.consultar(_db_setembro(), "2025-11", "2026-10", hoje=HOJE)
        self.assertEqual(len(r["comparativo"]), 12)
        self.assertEqual(r["comparativo"][-1]["situacao"], "em curso")
        self.assertEqual(r["comparativo"][-2]["situacao"], "calculado agora (nao fechado)")
        self.assertEqual(r["comparativo"][-2]["saldo"], 7172.4)

    def test_limites(self):
        with self.assertRaisesRegex(ValueError, "anterior"):
            hf.meses_entre("2026-10", "2026-09")
        with self.assertRaisesRegex(ValueError, "24"):
            hf.meses_entre("2024-01", "2026-12")
        self.assertEqual(hf.meses_entre("2025-12", "2026-01"), ["2025-12", "2026-01"])

    def test_mes_anterior(self):
        self.assertEqual(hf.mes_anterior(date(2026, 10, 10)), "2026-09")
        self.assertEqual(hf.mes_anterior(date(2027, 1, 10)), "2026-12")


class TestFerramentas(unittest.TestCase):
    def _ctx(self, db):
        ctx = mock.Mock()
        ctx.db = db
        return ctx

    def test_historico_padrao_e_doze_meses_ate_o_atual(self):
        from tools import hermes_tools

        with mock.patch.object(hermes_tools, "_hoje_brasilia", return_value=HOJE):
            r = hermes_tools.consultar_historico_financeiro(self._ctx(_db_setembro()), {})
        self.assertEqual([c["competencia"] for c in r["comparativo"]][::11], ["2025-11", "2026-10"])

    def test_fechar_pela_tool(self):
        from tools import hermes_tools

        with mock.patch.object(hermes_tools, "_hoje_brasilia", return_value=HOJE):
            r = hermes_tools.fechar_mes_financeiro(self._ctx(_db_setembro()), {"competencia": "2026-09"})
            erro = hermes_tools.fechar_mes_financeiro(self._ctx(_db_setembro()), {"competencia": "2026-10"})
        self.assertEqual(r["estado"], "verificado")
        self.assertIn("nao terminou", erro["erro"])


if __name__ == "__main__":
    unittest.main()
