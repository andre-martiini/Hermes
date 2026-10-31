"""Excluir entrada do diario de uma acao (28/10/2026)."""
import unittest

from tools import diario_acao, hermes_tools


class _Snap:
    def __init__(self, dados):
        self.exists, self._d = dados is not None, dados

    def to_dict(self):
        return dict(self._d or {})


class _Sub:
    def __init__(self):
        self.docs = []

    def add(self, doc):
        self.docs.append(doc)


class _Ref:
    def __init__(self, dados):
        self.dados, self.sub = dados, _Sub()

    def get(self):
        return _Snap(self.dados)

    def collection(self, nome):
        assert nome == "diario_removido"
        return self.sub

    def update(self, campos):
        for k, v in campos.items():
            if hasattr(v, "values"):  # ArrayRemove
                self.dados[k] = [e for e in self.dados[k] if e not in v.values]


class _Db:
    def __init__(self, dados):
        self.ref = _Ref(dados)

    def collection(self, nome):
        return self

    def document(self, doc_id):
        return self.ref


E1 = {"data": "2026-10-28T19:50:00.1+00:00", "nota": "ideia errada"}
E2 = {"data": "2026-10-28T20:00:00.2+00:00", "nota": "fica"}


class ExcluirEntradaDiarioTest(unittest.TestCase):
    def test_remove_so_a_entrada_e_guarda_copia(self):
        db = _Db({"acompanhamento": [E1, E2]})
        r = diario_acao.excluir_entrada(db, "t1", E1["data"])
        self.assertEqual(r["status"], "excluida")
        self.assertEqual(db.ref.dados["acompanhamento"], [E2])
        self.assertEqual(db.ref.sub.docs[0]["entrada"], E1)

    def test_data_inexistente_e_tarefa_inexistente(self):
        db = _Db({"acompanhamento": [E2]})
        self.assertIn("erro", diario_acao.excluir_entrada(db, "t1", "outra"))
        self.assertEqual(db.ref.dados["acompanhamento"], [E2])
        self.assertIn("erro", diario_acao.excluir_entrada(_Db(None), "t1", E1["data"]))
        self.assertIn("erro", diario_acao.excluir_entrada(db, "", E1["data"]))

    def test_tool_registrada(self):
        self.assertTrue(hermes_tools.has_tool("excluir_entrada_diario"))


if __name__ == "__main__":
    unittest.main()
