"""Rendas de servico: parcelas restantes, fim do contrato, aviso e projecao.

Os contratos sao os reais de out/2026 (Coordenacao Sigex e PLS MEC, mensais;
Workshop e sistema da clinica, pacote fechado).
"""

import unittest
from datetime import date
from unittest import mock

import rendas_servico as rs
from test_importar_fatura import _Db

HOJE = date(2026, 10, 12)


def _parcelas(datas_status, valor=4500.0):
    return [{"id": f"p{i}", "descricao": f"Parcela {i}", "valor": valor, "data_prevista": d, "status": s}
            for i, (d, s) in enumerate(datas_status, start=1)]


SIGEX = {
    "id": "sigex", "titulo": "Coordenação do Projeto Sigex", "cliente": "TJES", "status": "Ativo",
    "tipo_contrato": "Mensalidade", "valor_total": 54000, "data_termino": "2027-03-30",
    "parcelas": _parcelas([(f"2026-{m:02d}-05", "pago") for m in range(4, 11)]
                          + [("2026-11-05", "pendente"), ("2026-12-05", "pendente"),
                             ("2027-01-05", "pendente"), ("2027-02-05", "pendente"),
                             ("2027-03-05", "pendente")]),
}
PLS = {
    "id": "pls", "titulo": "Projeto PLS MEC", "status": "Ativo", "tipo_contrato": "Mensalidade",
    "valor_total": 35000, "data_termino": "2026-09-03",
    "parcelas": _parcelas([("2026-09-08", "pago"), ("2026-10-08", "pendente"), ("2026-11-08", "pendente"),
                           ("2026-12-08", "pendente"), ("2027-12-08", "pendente")], valor=3500.0),
}
WORKSHOP = {
    "id": "ws", "titulo": "Workshop Gestão de Pessoas", "status": "Ativo", "tipo_contrato": "Pacote Fechado",
    "valor_total": 3105.85, "data_termino": "2026-09-25",
    "parcelas": _parcelas([("2026-10-05", "pendente")], valor=3105.85),
}


class TestContrato(unittest.TestCase):
    def test_sigex(self):
        r = rs.resumir_contrato(SIGEX, HOJE)
        self.assertEqual((r["parcelas_pagas"], r["parcelas_total"], r["parcelas_restantes"]), (7, 12, 5))
        self.assertEqual((r["valor_restante"], r["termina_em"]), (22500.0, "2027-03-05"))
        self.assertEqual(r["proxima"]["data"], "2026-11-05")
        self.assertFalse(r["acabando"])
        self.assertEqual(r["inconsistencias"], [])

    def test_mensal_com_duas_parcelas_esta_acabando(self):
        sigex_fim = dict(SIGEX, parcelas=[dict(p, status="pago") for p in SIGEX["parcelas"][:10]]
                         + SIGEX["parcelas"][10:])
        self.assertTrue(rs.resumir_contrato(sigex_fim, HOJE)["acabando"])

    def test_pacote_fechado_nao_acaba(self):
        r = rs.resumir_contrato(WORKSHOP, HOJE)
        self.assertFalse(r["acabando"])
        self.assertEqual(r["atrasadas"], [{"id": "p1", "data": "2026-10-05", "valor": 3105.85, "descricao": "Parcela 1"}])
        self.assertEqual(r["pendentes"], [{"id": "p1", "data": "2026-10-05", "valor": 3105.85}])
        self.assertEqual(r["inconsistencias"], [])

    def test_inconsistencias_do_pls_mec(self):
        r = rs.resumir_contrato(PLS, HOJE)
        texto = " | ".join(r["inconsistencias"])
        self.assertIn("depois do término", texto)
        self.assertIn("parcelas somam R$ 17500.00", texto)
        self.assertIn("365 dias", texto)

    def test_ultima_parcela_no_mes_seguinte_ao_termino_e_normal(self):
        prorrogado = dict(PLS, valor_total=10500, data_termino="2026-12-31",
                          parcelas=_parcelas([("2026-11-08", "pendente"), ("2026-12-08", "pendente"),
                                              ("2027-01-08", "pendente")], valor=3500.0))
        self.assertEqual(rs.resumir_contrato(prorrogado, HOJE)["inconsistencias"], [])

    def test_todas_pagas_e_ainda_ativo(self):
        pago = dict(WORKSHOP, parcelas=[dict(WORKSHOP["parcelas"][0], status="pago")])
        self.assertIn("todas as parcelas pagas", rs.resumir_contrato(pago, HOJE)["inconsistencias"][0])


class TestProjecao(unittest.TestCase):
    def test_ifes_e_servicos_separados(self):
        p = rs.projetar([SIGEX, PLS, WORKSHOP], 9401.8, HOJE, meses=4)
        self.assertEqual([m["mes"] for m in p], ["2026-10", "2026-11", "2026-12", "2027-01"])
        self.assertTrue(all(m["ifes"] == 9401.8 for m in p))
        # Outubro: PLS e Workshop atrasados caem no mes atual.
        self.assertEqual(p[0]["servicos"], 3500.0 + 3105.85)
        self.assertTrue(all(d["atrasada"] for d in p[0]["detalhe"]))
        self.assertEqual(p[1]["servicos"], 4500.0 + 3500.0)
        self.assertEqual(p[3]["servicos"], 4500.0)
        self.assertEqual(p[1]["total"], 9401.8 + 8000.0)

    def test_atrasada_de_mes_anterior_cai_no_mes_atual(self):
        antigo = dict(WORKSHOP, parcelas=_parcelas([("2026-08-20", "pendente")], valor=500.0))
        p = rs.projetar([antigo], 0, HOJE, meses=2)
        self.assertEqual((p[0]["mes"], p[0]["servicos"]), ("2026-10", 500.0))

    def test_fora_do_horizonte_nao_entra(self):
        p = rs.projetar([PLS], 0, HOJE, meses=3)
        self.assertNotIn("2027-12", [m["mes"] for m in p])


class TestForaDaPrevisao(unittest.TestCase):
    """Parcela sem_previsao (ou pendente sem data) fica no contrato, mas sai das contas e da projecao."""

    def _sigex(self, **mudancas):
        parcelas = [dict(p) for p in SIGEX["parcelas"]]
        parcelas[7].update(mudancas)  # p8, 2026-11-05: a primeira pendente
        return dict(SIGEX, parcelas=parcelas)

    def test_resumo_nao_conta_a_parcela_marcada(self):
        r = rs.resumir_contrato(self._sigex(status="sem_previsao"), HOJE)
        self.assertEqual((r["parcelas_total"], r["parcelas_restantes"], r["valor_restante"]), (12, 4, 18000.0))
        self.assertEqual([p["id"] for p in r["sem_previsao"]], ["p8"])
        self.assertNotIn("p8", [p["id"] for p in r["pendentes"]])
        self.assertEqual(r["inconsistencias"], [])

    def test_termino_ignora_a_parcela_marcada(self):
        ultima = self._sigex(status="sem_previsao", data_prevista="2030-01-05")
        self.assertEqual(rs.resumir_contrato(ultima, HOJE)["termina_em"], "2027-03-05")

    def test_so_marcadas_restando_nao_diz_que_esta_tudo_pago(self):
        parcelas = [dict(p, status="pago") for p in SIGEX["parcelas"][:11]] + [dict(SIGEX["parcelas"][11],
                                                                                    status="sem_previsao")]
        r = rs.resumir_contrato(dict(SIGEX, parcelas=parcelas), HOJE)
        self.assertEqual((r["parcelas_restantes"], r["acabando"], r["inconsistencias"]), (0, False, []))

    def test_pendente_sem_data_nao_e_proxima_nem_atrasada(self):
        r = rs.resumir_contrato(self._sigex(data_prevista=""), HOJE)
        self.assertEqual(r["parcelas_restantes"], 5)
        self.assertEqual(r["proxima"]["id"], "p9")
        self.assertEqual([p["data"] for p in r["pendentes"]].count(None), 1)

    def test_projecao_ignora_marcada_e_sem_data(self):
        cheia = rs.projetar([SIGEX], 0, HOJE, meses=3)
        marcada = rs.projetar([self._sigex(status="sem_previsao")], 0, HOJE, meses=3)
        sem_data = rs.projetar([self._sigex(data_prevista="")], 0, HOJE, meses=3)
        self.assertEqual([m["servicos"] for m in cheia], [0.0, 4500.0, 4500.0])
        self.assertEqual([m["servicos"] for m in marcada], [0.0, 0.0, 4500.0])
        self.assertEqual(marcada, sem_data)

    def test_posicao_da_parcela_nao_conta_a_marcada_nas_restantes(self):
        sigex = self._sigex(status="sem_previsao")
        self.assertEqual(rs.posicao_da_parcela(sigex, "p7")["parcelas_restantes"], 4)

    def test_fora_da_previsao(self):
        self.assertTrue(rs.fora_da_previsao({"status": "sem_previsao", "data_prevista": "2026-11-05"}))
        self.assertTrue(rs.fora_da_previsao({"status": "pendente", "data_prevista": ""}))
        self.assertFalse(rs.fora_da_previsao({"status": "pendente", "data_prevista": "2026-11-05T00:00:00.000Z"}))
        self.assertFalse(rs.fora_da_previsao({"status": "pago", "data_prevista": ""}))


class TestFontes(unittest.TestCase):
    def test_renda_ifes_e_a_ultima_recebida(self):
        db = _Db({"income_entries": {
            "a": {"description": "Remuneração IFES", "category": "Renda Principal", "year": 2026, "month": 8,
                  "amount": 9096.95, "isReceived": True},
            "b": {"description": "Remuneração IFES", "category": "Renda Principal", "year": 2026, "month": 9,
                  "amount": 9401.8, "isReceived": True},
            "c": {"description": "Remuneração IFES", "category": "Renda Principal", "year": 2026, "month": 10,
                  "amount": 9500, "isReceived": False},
            # Renda Principal mais recente que nao e salario.
            "d": {"description": "Diárias Facto", "category": "Renda Principal", "year": 2026, "month": 10,
                  "amount": 980, "isReceived": True},
        }})
        self.assertEqual(rs.renda_ifes_atual(db), (9401.8, "2026-10"))

    def test_posicao_da_parcela(self):
        self.assertEqual(rs.posicao_da_parcela(SIGEX, "p7"),
                         {"parcela": "7/12", "parcelas_restantes": 5, "termina_em": "2027-03-05"})
        self.assertIsNone(rs.posicao_da_parcela(SIGEX, "nao-existe"))

    def test_so_contratos_ativos(self):
        db = _Db({"servicos": {"a": dict(SIGEX), "b": dict(WORKSHOP, status="Concluído")}})
        self.assertEqual([c["id"] for c in rs.contratos_ativos(db)], ["a"])


class TestAviso(unittest.TestCase):
    def test_item_da_fila_de_atencao(self):
        sigex_fim = dict(SIGEX, parcelas=[dict(p, status="pago") for p in SIGEX["parcelas"][:10]]
                         + SIGEX["parcelas"][10:])
        itens = rs.itens_atencao([rs.resumir_contrato(sigex_fim, HOJE)], HOJE)
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertEqual((item["origem"], item["tipo"]), ("financeiro", "renda_servico_acabando"))
        self.assertEqual(item["chave_dedupe"], "renda_servico_acabando:sigex:2027-03-05")
        self.assertIn("2 parcela", item["titulo"])

    def test_detector_financeiro_inclui_o_aviso(self):
        import atencao

        sigex_fim = dict(SIGEX, parcelas=[dict(p, status="pago") for p in SIGEX["parcelas"][:10]]
                         + SIGEX["parcelas"][10:])
        db = _Db({"servicos": {"sigex": sigex_fim}})
        with mock.patch.object(atencao, "_persistir_itens_atencao") as persistir:
            itens = atencao.detectar_atencao_financeiro(
                db, hoje=HOJE, settings={"atencao": {"financeiro": {"enabled": True}}})
        self.assertEqual([i["tipo"] for i in itens], ["renda_servico_acabando"])
        persistir.assert_called_once()

    def test_falha_nas_rendas_nao_cala_as_contas(self):
        import atencao

        with mock.patch.object(rs, "contratos_ativos", side_effect=RuntimeError("fora")), \
             mock.patch.object(atencao, "_persistir_itens_atencao"):
            itens = atencao.detectar_atencao_financeiro(
                _Db(), hoje=HOJE, settings={"atencao": {"financeiro": {"enabled": True}}})
        self.assertEqual(itens, [])


class TestConsultaFinancas(unittest.TestCase):
    def test_renda_de_servico_ganha_a_posicao(self):
        from tools import telegram_extended

        db = _Db({
            "servicos": {"sigex": dict(SIGEX)},
            "income_entries": {"r7": {"description": "Coordenação do Projeto Sigex - Parcela 7", "amount": 4500,
                                      "month": 9, "year": 2026, "status": "active", "isReceived": True,
                                      "service_id": "sigex", "parcela_id": "p7"}},
            "finance_settings": {"config": {}},
        })
        import json

        r = json.loads(telegram_extended.execute("consultar_financas_v2", {"mes": 9, "ano": 2026}, db=db))
        renda = r["detalhes"]["rendas"][0]
        self.assertEqual((renda["parcela"], renda["parcelas_restantes"]), ("7/12", 5))


class TestExclusaoComLeiturasParalelas(unittest.TestCase):
    """30/10/2026: renda excluida de parcela pendente voltava duplicada na leitura seguinte do financeiro.

    O que recriava era a tela (index.tsx), nao a leitura; aqui fica travado que ler o
    financeiro, mesmo em paralelo, nunca cria nem reativa renda (a tela e coberta em
    src/utils/rendasDeServico.test.ts).
    """

    def _db(self):
        return _Db({
            "servicos": {"pls": dict(PLS, parcelas=_parcelas([("2026-09-08", "pago"), ("2026-10-08", "pago"),
                                                              ("2026-11-08", "pendente")], valor=3500.0))},
            "income_entries": {"r8": {"description": "Projeto PLS MEC - Parcela 3", "amount": 3500.0, "month": 10,
                                      "year": 2026, "status": "active", "isReceived": False,
                                      "service_id": "pls", "parcela_id": "p3"}},
            "finance_settings": {"config": {}},
        })

    def _ler_em_paralelo(self, db, vezes=8):
        import json
        from concurrent.futures import ThreadPoolExecutor

        from tools import telegram_extended

        def ler(_):
            return json.loads(telegram_extended.execute("consultar_financas_v2", {"mes": 10, "ano": 2026}, db=db))

        with ThreadPoolExecutor(max_workers=vezes) as pool:
            return list(pool.map(ler, range(vezes)))

    def _ativas(self, db, parcela_id="p3"):
        return [i for i, d in db.banco["income_entries"].items()
                if d.get("parcela_id") == parcela_id and d.get("status") != "deleted"]

    def test_excluir_e_ler_em_paralelo_nao_recria_a_renda(self):
        from tools import financas_itens

        db = self._db()
        financas_itens.excluir(db, {"tipo": "renda", "id": "r8"})
        leituras = self._ler_em_paralelo(db)
        self.assertEqual(self._ativas(db), [])
        self.assertEqual(len(db.banco["income_entries"]), 1)
        self.assertTrue(all(l["detalhes"]["rendas"] == [] and l["resumo"]["total_renda"] == 0 for l in leituras))

    def test_parcela_sem_previsao_fica_com_zero_rendas_ativas_e_fora_da_projecao(self):
        from tools import financas_itens

        db = self._db()
        financas_itens.editar_parcela_servico(db, {"service_id": "pls", "parcela_id": "p3", "status": "sem_previsao"})
        self._ler_em_paralelo(db)
        self.assertEqual(self._ativas(db), [])
        projecao = rs.resumo(db, date(2026, 10, 30), meses=3)["projecao"]
        self.assertEqual([m["servicos"] for m in projecao], [0.0, 0.0, 0.0])


class TestFerramenta(unittest.TestCase):
    def test_resumo_pela_tool(self):
        from tools import hermes_tools

        ctx = mock.Mock()
        ctx.db = _Db({"servicos": {"sigex": dict(SIGEX)}})
        r = hermes_tools.consultar_rendas_servico(ctx, {"meses": 3})
        self.assertEqual(len(r["projecao"]), 3)
        self.assertEqual(r["contratos"][0]["titulo"], "Coordenação do Projeto Sigex")


if __name__ == "__main__":
    unittest.main()
