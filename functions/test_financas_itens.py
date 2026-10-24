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
                       "status": "active", "parcela_id": "p8", "isReceived": False},
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
