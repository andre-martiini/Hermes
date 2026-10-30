"""Editar/excluir lançamento, parcela de serviço, mês sem ambiguidade e aviso de duplicata (24/10/2026)."""
import unittest
from unittest.mock import patch

from tools import financas_itens
from tools import hermes_tools


class _Snap:
    def __init__(self, col, doc_id):
        self._col, self.id = col, doc_id
        self.exists = doc_id in col.docs
        self.reference = _Ref(col, doc_id)

    def to_dict(self):
        return dict(self._col.docs.get(self.id) or {})


class _Ref:
    def __init__(self, col, doc_id):
        self._col, self.id = col, doc_id

    def get(self):
        return _Snap(self._col, self.id)

    def update(self, campos):
        self._col.docs[self.id].update(campos)

    def delete(self):
        self._col.docs.pop(self.id, None)


class _Col:
    def __init__(self, docs=None, filtros=()):
        self.docs, self._filtros = docs if docs is not None else {}, filtros

    def document(self, doc_id):
        return _Ref(self, doc_id)

    def where(self, campo, op, valor):
        return _Col(self.docs, self._filtros + ((campo, valor),))

    def stream(self):
        return [_Snap(self, i) for i, d in list(self.docs.items())
                if all(d.get(c) == v for c, v in self._filtros)]


class _Db:
    def __init__(self, dados):
        self._cols = {nome: _Col(docs) for nome, docs in dados.items()}

    def collection(self, nome):
        return self._cols.setdefault(nome, _Col())


class _Ctx:
    def __init__(self, db):
        self.db, self.task_id = db, None


def _db():
    return _Db({
        "income_entries": {
            "dez": {"description": "Remuneração Ifes", "amount": 9441.10, "month": 11, "year": 2026, "status": "active"},
            "nov": {"description": "Remuneração Ifes", "amount": 9441.10, "month": 10, "year": 2026, "status": "active"},
            "ligada": {"description": "[Serviço: Sigex] Parcela 8", "amount": 4500, "month": 10, "year": 2026,
                       "status": "active", "parcela_id": "p8", "service_id": "sigex", "isReceived": False},
        },
        "fixed_bills": {"luz": {"description": "Luz", "amount": 200, "month": 9, "year": 2026}},
        "servicos": {"sigex": {"parcelas": [
            {"id": "p7", "valor": 4500, "data_prevista": "2026-10-10", "status": "pago"},
            {"id": "p8", "valor": 4500, "data_prevista": "2026-11-10", "status": "pendente"}]}},
    })


class TestEditarExcluir(unittest.TestCase):
    def test_editar_corrige_mes_e_devolve_antes_e_depois(self):
        db = _db()
        r = financas_itens.editar(db, {"tipo": "renda", "id": "dez", "competencia": "2026-11"})
        self.assertEqual(r["alterado"]["month"], [11, 10])
        self.assertEqual(r["periodo"]["mes_nome"], "novembro")
        self.assertEqual(db.collection("income_entries").docs["dez"]["month"], 10)

    def test_editar_sem_campo_e_tipo_invalido_dao_erro(self):
        self.assertIn("erro", financas_itens.editar(_db(), {"tipo": "renda", "id": "nov"}))
        self.assertIn("erro", financas_itens.editar(_db(), {"tipo": "x", "id": "nov", "valor": 1}))
        self.assertIn("erro", financas_itens.editar(_db(), {"tipo": "renda", "id": "nao-existe", "valor": 1}))

    def test_excluir_renda_e_reversivel_conta_fixa_sai_de_vez(self):
        db = _db()
        r = financas_itens.excluir(db, {"tipo": "renda", "id": "dez"})
        self.assertTrue(r["reversivel"])
        self.assertEqual(db.collection("income_entries").docs["dez"]["status"], "deleted")
        self.assertIn("erro", financas_itens.excluir(db, {"tipo": "renda", "id": "dez"}))  # já excluído
        r = financas_itens.excluir(db, {"tipo": "obrigacao_fixa", "id": "luz"})
        self.assertFalse(r["reversivel"])
        self.assertNotIn("luz", db.collection("fixed_bills").docs)

    def test_parcela_adiada_e_pendente_atualiza_renda_ligada(self):
        db = _db()
        r = financas_itens.editar_parcela_servico(db, {"service_id": "sigex", "parcela_id": "p8",
                                                       "data_prevista": "2026-12-15"})
        self.assertEqual(r["alterado"], {"data_prevista": ["2026-11-10", "2026-12-15"]})
        self.assertEqual(r["rendas_atualizadas"], ["ligada"])
        renda = db.collection("income_entries").docs["ligada"]
        self.assertEqual((renda["month"], renda["year"], renda["day"], renda["isReceived"]), (11, 2026, 15, False))
        self.assertIn("erro", financas_itens.editar_parcela_servico(db, {"service_id": "sigex", "parcela_id": "p8",
                                                                         "status": "talvez"}))


def _parcela(db, parcela_id="p8"):
    return next(p for p in db.collection("servicos").docs["sigex"]["parcelas"] if p["id"] == parcela_id)


class TestParcelaForaDaPrevisao(unittest.TestCase):
    """30/10/2026: renda excluida voltava duas vezes; faltava um jeito de tirar a parcela da previsao."""

    def test_sem_previsao_retira_a_renda_e_pendente_devolve(self):
        db = _db()
        r = financas_itens.editar_parcela_servico(db, {"service_id": "sigex", "parcela_id": "p8",
                                                       "status": "sem_previsao"})
        self.assertEqual((r["rendas_retiradas"], r["rendas_atualizadas"]), (["ligada"], []))
        self.assertEqual(_parcela(db)["status"], "sem_previsao")
        renda = db.collection("income_entries").docs["ligada"]
        self.assertEqual((renda["status"], renda["retirada_por"]), ("deleted", "previsao"))

        r = financas_itens.editar_parcela_servico(db, {"service_id": "sigex", "parcela_id": "p8",
                                                       "status": "pendente"})
        self.assertEqual((r["rendas_reativadas"], r["rendas_retiradas"]), (["ligada"], []))
        renda = db.collection("income_entries").docs["ligada"]
        self.assertEqual((renda["status"], renda["retirada_por"], renda["month"], renda["day"]),
                         ("active", None, 10, 10))

    def test_parcela_paga_nao_sai_da_previsao(self):
        db = _db()
        r = financas_itens.editar_parcela_servico(db, {"service_id": "sigex", "parcela_id": "p7",
                                                       "status": "sem_previsao"})
        self.assertIn("erro", r)
        self.assertEqual(_parcela(db, "p7")["status"], "pago")

    def test_limpar_a_data_tira_da_previsao_e_nova_data_devolve(self):
        db = _db()
        r = financas_itens.editar_parcela_servico(db, {"service_id": "sigex", "parcela_id": "p8",
                                                       "limpar_data_prevista": True})
        self.assertEqual(r["alterado"], {"data_prevista": ["2026-11-10", ""]})
        self.assertEqual(r["rendas_retiradas"], ["ligada"])
        self.assertIn("sem data_prevista", r["aviso"])

        r = financas_itens.editar_parcela_servico(db, {"service_id": "sigex", "parcela_id": "p8",
                                                       "data_prevista": "2026-12-15"})
        self.assertEqual(r["rendas_reativadas"], ["ligada"])
        renda = db.collection("income_entries").docs["ligada"]
        self.assertEqual((renda["status"], renda["month"], renda["year"], renda["day"]), ("active", 11, 2026, 15))

    def test_data_e_limpar_data_juntos_dao_erro(self):
        r = financas_itens.editar_parcela_servico(_db(), {"service_id": "sigex", "parcela_id": "p8",
                                                          "data_prevista": "2026-12-15", "limpar_data_prevista": True})
        self.assertIn("erro", r)

    def test_reativar_nao_traz_de_volta_renda_de_duplicata(self):
        db = _db()
        db.collection("income_entries").docs["ligada"].update({"status": "deleted", "retirada_por": "duplicata"})
        db.collection("servicos").docs["sigex"]["parcelas"][1]["status"] = "sem_previsao"
        r = financas_itens.editar_parcela_servico(db, {"service_id": "sigex", "parcela_id": "p8",
                                                       "status": "pendente"})
        self.assertEqual(r["rendas_reativadas"], [])
        self.assertEqual(db.collection("income_entries").docs["ligada"]["status"], "deleted")

    def test_adiar_nao_ressuscita_renda_que_o_usuario_excluiu(self):
        db = _db()
        financas_itens.excluir(db, {"tipo": "renda", "id": "ligada"})
        r = financas_itens.editar_parcela_servico(db, {"service_id": "sigex", "parcela_id": "p8",
                                                       "data_prevista": "2026-12-15"})
        self.assertEqual((r["rendas_atualizadas"], r["rendas_reativadas"]), ([], []))
        self.assertEqual(db.collection("income_entries").docs["ligada"]["status"], "deleted")

    def test_sem_previsao_e_pendente_recupera_a_renda_que_o_usuario_excluiu(self):
        db = _db()
        financas_itens.excluir(db, {"tipo": "renda", "id": "ligada"})
        for status in ("sem_previsao", "pendente"):
            r = financas_itens.editar_parcela_servico(db, {"service_id": "sigex", "parcela_id": "p8",
                                                           "status": status})
        self.assertEqual(r["rendas_reativadas"], ["ligada"])
        self.assertEqual(db.collection("income_entries").docs["ligada"]["status"], "active")

    def test_excluir_renda_de_parcela_pendente_avisa_da_projecao(self):
        db = _db()
        r = financas_itens.excluir(db, {"tipo": "renda", "id": "ligada"})
        self.assertIn("sem_previsao", r["aviso"])

    def test_excluir_copia_extra_ou_renda_de_parcela_paga_nao_avisa(self):
        db = _db()
        db.collection("income_entries").docs["copia"] = dict(db.collection("income_entries").docs["ligada"])
        self.assertNotIn("aviso", financas_itens.excluir(db, {"tipo": "renda", "id": "copia"}))
        db.collection("servicos").docs["sigex"]["parcelas"][1]["status"] = "pago"
        self.assertNotIn("aviso", financas_itens.excluir(db, {"tipo": "renda", "id": "ligada"}))


class TestDeduplicarRendas(unittest.TestCase):
    def _rendas(self):
        base = {"description": "[Serviço: PLS MEC] Parcela 8", "amount": 3500, "service_id": "pls",
                "parcela_id": "8n3849jxq", "month": 10, "year": 2026, "status": "active", "isReceived": False}
        return {
            "a": {**base, "data_criacao": "2026-10-30T10:59:22.044Z"},
            "b": {**base, "data_criacao": "2026-10-30T10:59:22.045Z"},
            "outro_mes": {**base, "month": 11, "data_criacao": "2026-10-30T11:00:00.000Z"},
            "excluida": {**base, "status": "deleted", "data_criacao": "2026-10-29T10:00:00.000Z"},
            "sem_vinculo": {"description": "Remuneração Ifes", "amount": 9441.10, "month": 10, "year": 2026,
                            "status": "active"},
        }

    def test_simulacao_lista_e_nao_grava(self):
        db = _Db({"income_entries": self._rendas()})
        r = financas_itens.deduplicar_rendas_servico(db, {})
        self.assertEqual((r["modo"], r["grupos_duplicados"], r["rendas_extras"]), ("simulacao", 1, 1))
        grupo = r["mudancas"][0]
        self.assertEqual((grupo["competencia"], grupo["mantida"]["id"], [e["id"] for e in grupo["extras"]]),
                         ("2026-11", "a", ["b"]))
        self.assertEqual(db.collection("income_entries").docs["b"]["status"], "active")

    def test_aplicar_marca_so_a_extra_e_repetir_nao_acha_mais(self):
        db = _Db({"income_entries": self._rendas()})
        r = financas_itens.deduplicar_rendas_servico(db, {"simular": False})
        self.assertEqual((r["modo"], r["rendas_extras"]), ("aplicado", 1))
        docs = db.collection("income_entries").docs
        self.assertEqual((docs["b"]["status"], docs["b"]["retirada_por"], docs["b"]["duplicata_de"]),
                         ("deleted", "duplicata", "a"))
        self.assertEqual([docs[i]["status"] for i in ("a", "outro_mes", "sem_vinculo")], ["active"] * 3)
        self.assertEqual(financas_itens.deduplicar_rendas_servico(db, {"simular": False})["grupos_duplicados"], 0)

    def test_mantem_a_ja_recebida_mesmo_sendo_mais_nova(self):
        rendas = self._rendas()
        rendas["b"]["isReceived"] = True
        db = _Db({"income_entries": rendas})
        r = financas_itens.deduplicar_rendas_servico(db, {"simular": False})
        self.assertEqual(r["mudancas"][0]["mantida"]["id"], "b")
        self.assertEqual(db.collection("income_entries").docs["a"]["status"], "deleted")

    def test_pela_tool_do_mcp_a_simulacao_e_o_padrao(self):
        db = _Db({"income_entries": self._rendas()})
        r = hermes_tools.deduplicar_rendas_servico(_Ctx(db), {})
        self.assertEqual(r["modo"], "simulacao")


class TestCanalMcp(unittest.TestCase):
    def test_mes_cru_e_recusado_no_mcp(self):
        ctx = _Ctx(_db())
        r = hermes_tools._registrar_item_financeiro_v2(ctx, {"tipo": "renda", "descricao": "X", "valor": 1, "mes": 11})
        self.assertIn("competencia", r["erro"])
        r = hermes_tools._via_telegram("consultar_financas_v2")(ctx, {"mes": 10})
        self.assertIn("competencia", r["erro"])

    def test_duplicata_avisa_e_confirmar_cria(self):
        ctx = _Ctx(_db())
        args = {"tipo": "renda", "descricao": "remuneracao  IFES", "valor": 9441.10, "competencia": "2026-11"}
        r = hermes_tools._registrar_item_financeiro_v2(ctx, args)
        self.assertEqual(r["status"], "possivel_duplicata")
        self.assertEqual([e["id"] for e in r["existentes"]], ["nov"])
        with patch("tools.telegram_extended.execute", return_value='{"success": true}') as execute:
            hermes_tools._registrar_item_financeiro_v2(ctx, {**args, "confirmar_duplicata": True})
        slots = execute.call_args[0][1]
        self.assertNotIn("confirmar_duplicata", slots)
        self.assertEqual(slots["categoria"], "Geral")


if __name__ == "__main__":
    unittest.main()
