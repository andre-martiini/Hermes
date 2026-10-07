"""Ideias (tela Brainstorming): o que o MCP grava tem de aparecer na tela igual
ao que o app grava -- mesma colecao, mesmo formato de `timestamp` (a tela ordena
por string), `status` 'active'. Sem rede e sem Firestore."""

import unittest

from test_lista_compras import _Db
from tools import hermes_tools, ideias
from tools.tool_context import ToolContext


def _ctx(db):
    return ToolContext(_db=db)


class TestGuardar(unittest.TestCase):
    def test_grava_no_formato_do_app(self):
        db = _Db()
        r = ideias.guardar(db, "  app de receitas  ")
        doc = db.collection(ideias.COLECAO).dados[r["id"]]
        self.assertEqual(doc["text"], "app de receitas")
        self.assertEqual(doc["status"], "active")
        self.assertEqual(doc["origem"], "mcp")
        # Mesmo formato de `new Date().toISOString()`.
        self.assertRegex(doc["timestamp"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
        self.assertEqual(r, {"id": r["id"], "texto": "app de receitas", "timestamp": doc["timestamp"]})

    def test_contexto_vai_em_linha_nova(self):
        r = ideias.guardar(_Db(), "ideia", contexto="reuniao com Joao")
        self.assertEqual(r["texto"], "ideia\nContexto: reuniao com Joao")

    def test_handler_devolve_erro_prefixado(self):
        db = _Db()
        self.assertTrue(hermes_tools.execute("guardar_ideia", {"texto": "   "}, _ctx(db)).startswith("ERRO|"))
        longo = hermes_tools.execute("guardar_ideia", {"texto": "x" * 4001}, _ctx(db))
        self.assertTrue(longo.startswith("ERRO|"))
        self.assertEqual(db.collection(ideias.COLECAO).dados, {})


class TestListar(unittest.TestCase):
    def setUp(self):
        self.db = _Db()
        self.db.collection(ideias.COLECAO).dados.update({
            "a": {"text": "Ideia de Ação antiga", "timestamp": "2026-01-01T00:00:00.000Z", "status": "active"},
            "b": {"text": "nova", "timestamp": "2026-05-01T00:00:00.000Z"},  # sem status = ativa
            "c": {"text": "arquivada acao", "timestamp": "2026-03-01T00:00:00.000Z", "status": "archived"},
        })

    def test_padrao_ativas_mais_recentes_primeiro(self):
        r = ideias.listar(self.db)
        self.assertEqual([i["id"] for i in r["ideias"]], ["b", "a"])
        self.assertEqual(r["ideias"][0], {"id": "b", "texto": "nova", "data": "2026-05-01T00:00:00.000Z", "status": "active"})

    def test_busca_ignora_acento_e_caixa(self):
        r = ideias.listar(self.db, busca="ACAO", status="todas")
        self.assertEqual([i["id"] for i in r["ideias"]], ["c", "a"])

    def test_archived_e_limite(self):
        self.assertEqual([i["id"] for i in ideias.listar(self.db, status="archived")["ideias"]], ["c"])
        r = ideias.listar(self.db, status="todas", limite=1)
        self.assertEqual((r["total"], r["retornados"], r["ideias"][0]["id"]), (3, 1, "b"))
        self.assertEqual(ideias.listar(self.db, limite=999)["retornados"], 2)

    def test_status_invalido_vira_erro(self):
        r = hermes_tools.execute("listar_ideias", {"status": "xyz"}, _ctx(self.db))
        self.assertTrue(r.startswith("ERRO|"))

    def test_guardada_aparece_na_listagem(self):
        g = ideias.guardar(self.db, "mais nova")
        self.assertEqual(ideias.listar(self.db)["ideias"][0]["id"], g["id"])


if __name__ == "__main__":
    unittest.main()
