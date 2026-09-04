"""Testes unitários para functions/agent_runs.py (PR 2, Fase 1).

Cobre:
- Lógica pura de montar_registro (campos obrigatórios, validação de status e erro condicional)
- registrar grava documento na coleção agent_runs com timestamps e retorna run_id
- listar_recentes filtra por rotina e ordena por criado_em decrescente
"""

from datetime import datetime, timezone
import unittest

import agent_runs as runs_mod


class _MockDocSnap:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = dict(data) if data is not None else None
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else {}


class _MockDocRef:
    def __init__(self, col, doc_id: str):
        self.col = col
        self.id = doc_id

    def get(self):
        data = self.col._docs.get(self.id)
        return _MockDocSnap(self.id, data)


class _MockQuery:
    def __init__(self, col, items):
        self.col = col
        self.items = items

    def where(self, field, op, val):
        filtered = [
            (k, v) for k, v in self.items
            if op == "==" and v.get(field) == val
        ]
        return _MockQuery(self.col, filtered)

    def stream(self):
        return [_MockDocSnap(k, v) for k, v in self.items]


class _MockCollection:
    def __init__(self, db, name: str):
        self.db = db
        self.name = name
        self._docs: dict[str, dict] = {}
        self._counter = 1

    def document(self, doc_id: str):
        return _MockDocRef(self, doc_id)

    def add(self, data):
        doc_id = f"run_{self._counter}"
        self._counter += 1
        self._docs[doc_id] = dict(data)
        return (datetime.now(timezone.utc), _MockDocRef(self, doc_id))

    def where(self, field, op, val):
        filtered = [
            (k, v) for k, v in self._docs.items()
            if op == "==" and v.get(field) == val
        ]
        return _MockQuery(self, filtered)

    def stream(self):
        return [_MockDocSnap(k, v) for k, v in self._docs.items()]


class _MockDB:
    def __init__(self):
        self._collections: dict[str, _MockCollection] = {}

    def collection(self, name: str) -> _MockCollection:
        if name not in self._collections:
            self._collections[name] = _MockCollection(self, name)
        return self._collections[name]


class TestMontarRegistro(unittest.TestCase):
    def test_registro_valido_sucesso(self):
        reg = runs_mod.montar_registro(
            rotina="briefing_matinal",
            resumo="Briefing matinal executado, 3 decisões geradas.",
            contadores={"itens_lidos": 5, "decisoes": 3},
        )
        self.assertEqual(reg["rotina"], "briefing_matinal")
        self.assertEqual(reg["resumo"], "Briefing matinal executado, 3 decisões geradas.")
        self.assertEqual(reg["status"], "sucesso")
        self.assertEqual(reg["contadores"]["decisoes"], 3)
        self.assertIsNone(reg["erro"])

    def test_registro_valido_erro(self):
        reg = runs_mod.montar_registro(
            rotina="varredura_followups",
            resumo="Falha na leitura do outbox.",
            status="erro",
            erro="Timeout de conexão Firestore",
        )
        self.assertEqual(reg["status"], "erro")
        self.assertEqual(reg["erro"], "Timeout de conexão Firestore")

    def test_registro_valido_parcial(self):
        reg = runs_mod.montar_registro(
            rotina="executor_agent_requests",
            resumo="Processou 2 de 3 pedidos com sucesso.",
            status="parcial",
            contadores={"sucesso": 2, "erro": 1},
        )
        self.assertEqual(reg["status"], "parcial")

    def test_rotina_obrigatoria(self):
        res1 = runs_mod.montar_registro(rotina="", resumo="Algo")
        self.assertIn("erro", res1)
        res2 = runs_mod.montar_registro(rotina=None, resumo="Algo")
        self.assertIn("erro", res2)

    def test_resumo_obrigatorio(self):
        res1 = runs_mod.montar_registro(rotina="teste", resumo="")
        self.assertIn("erro", res1)
        res2 = runs_mod.montar_registro(rotina="teste", resumo=None)
        self.assertIn("erro", res2)

    def test_status_invalido(self):
        res = runs_mod.montar_registro(rotina="teste", resumo="algo", status="invalido")
        self.assertIn("erro", res)

    def test_erro_obrigatorio_quando_status_erro(self):
        res = runs_mod.montar_registro(rotina="teste", resumo="falhou", status="erro")
        self.assertIn("erro", res)
        self.assertIn("obrigatório quando status é 'erro'", res["erro"])

    def test_contadores_deve_ser_dict(self):
        res = runs_mod.montar_registro(rotina="teste", resumo="algo", contadores="invalido")
        self.assertIn("erro", res)


class TestRegistrar(unittest.TestCase):
    def setUp(self):
        self.db = _MockDB()

    def test_registrar_com_sucesso(self):
        res = runs_mod.registrar(
            self.db,
            rotina="briefing_matinal",
            resumo="Executou sem problemas.",
            contadores={"acoes_vistas": 10},
        )
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["run_id"], "run_1")

        snap = self.db.collection(runs_mod.COLLECTION).document("run_1").get()
        self.assertTrue(snap.exists)
        d = snap.to_dict()
        self.assertEqual(d["rotina"], "briefing_matinal")
        self.assertEqual(d["status"], "sucesso")
        self.assertEqual(d["contadores"]["acoes_vistas"], 10)

    def test_registrar_com_dados_invalidos_retorna_erro(self):
        res = runs_mod.registrar(self.db, rotina="", resumo="algo")
        self.assertIn("erro", res)
        self.assertEqual(len(self.db.collection(runs_mod.COLLECTION)._docs), 0)


class TestListarRecentes(unittest.TestCase):
    def setUp(self):
        self.db = _MockDB()
        col = self.db.collection(runs_mod.COLLECTION)
        col._docs["run_1"] = {
            "rotina": "briefing",
            "status": "sucesso",
            "resumo": "Briefing matinal 1",
            "criado_em": datetime(2026, 9, 3, 6, 45, tzinfo=timezone.utc),
        }
        col._docs["run_2"] = {
            "rotina": "varredura",
            "status": "sucesso",
            "resumo": "Varredura tarde",
            "criado_em": datetime(2026, 9, 3, 17, 30, tzinfo=timezone.utc),
        }
        col._docs["run_3"] = {
            "rotina": "briefing",
            "status": "sucesso",
            "resumo": "Briefing matinal 2",
            "criado_em": datetime(2026, 9, 4, 6, 45, tzinfo=timezone.utc),
        }

    def test_listar_todos_ordenado_decrescente(self):
        res = runs_mod.listar_recentes(self.db)
        self.assertEqual(res["total"], 3)
        # Mais recente primeiro: run_3 (dia 4, 6h45), run_2 (dia 3, 17h30), run_1 (dia 3, 6h45)
        self.assertEqual(res["runs"][0]["id"], "run_3")
        self.assertEqual(res["runs"][1]["id"], "run_2")
        self.assertEqual(res["runs"][2]["id"], "run_1")

    def test_listar_com_filtro_rotina(self):
        res = runs_mod.listar_recentes(self.db, rotina="briefing")
        self.assertEqual(res["total"], 2)
        self.assertEqual(res["runs"][0]["id"], "run_3")
        self.assertEqual(res["runs"][1]["id"], "run_1")


if __name__ == "__main__":
    unittest.main()
