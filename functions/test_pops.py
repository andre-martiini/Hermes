"""POPs pelo MCP (tools/pops.py): os critérios de aceite do pedido de 31/10/2026."""
import unittest

import main
from fake_firestore_transcricao import FakeDb
from tools import hermes_tools, pops


def _ativos(db):
    """O que `obter_estado_atual` põe em `pops_ativos` (sem o cache de 60 s)."""
    main._POPS_DATA_CACHE = None
    return {p["id"]: p for p in main._pops_sempre_ativos(db)}


class TestPops(unittest.TestCase):
    def setUp(self):
        self.db = FakeDb()

    def _criar(self, **extra):
        r = pops.criar(self.db, {"titulo": "Post da Semana", "instrucao_sistema": "Toda segunda, rascunho.", **extra})
        self.assertEqual(r["status"], "criado", r)
        return r["id"]

    def test_1_criado_aparece_em_pops_ativos(self):
        pop_id = self._criar()
        pop = _ativos(self.db)[pop_id]
        self.assertEqual(pop["instrucao_sistema"], "Toda segunda, rascunho.")
        self.assertEqual((pop["autor"], pop["gatilhos"]), ("agente", []))
        self.assertTrue(pop["criado_em"])

    def test_por_gatilhos_nao_entra_em_pops_ativos(self):
        pop_id = self._criar(origem="gatilhos", gatilhos=["post"])
        self.assertNotIn(pop_id, _ativos(self.db))

    def test_2_editar_muda_texto_e_guarda_anterior(self):
        pop_id = self._criar()
        r = pops.editar(self.db, {"id": pop_id, "instrucao_sistema": "Toda terça."})
        self.assertEqual(r["anterior"], {"instrucao_sistema": "Toda segunda, rascunho."})
        self.assertEqual(_ativos(self.db)[pop_id]["instrucao_sistema"], "Toda terça.")
        hist = pops.listar(self.db, {"id": pop_id})["historico"]
        self.assertEqual([h["operacao"] for h in hist], ["criar", "editar"])
        self.assertEqual(hist[-1]["antes"], {"instrucao_sistema": "Toda segunda, rascunho."})

    def test_3_desativar_tira_de_pops_ativos_sem_perder_e_reativa(self):
        pop_id = self._criar()
        self.assertEqual(pops.desativar(self.db, {"id": pop_id})["status"], "desativado")
        self.assertNotIn(pop_id, _ativos(self.db))
        inativos = pops.listar(self.db, {"filtro": "inativos"})["pops"]
        self.assertEqual([(p["id"], p["ativo"]) for p in inativos], [(pop_id, False)])
        self.assertEqual(pops.listar(self.db, {"filtro": "ativos"})["pops"], [])
        self.assertEqual(pops.desativar(self.db, {"id": pop_id})["status"], "sem_mudanca")
        self.assertEqual(pops.desativar(self.db, {"id": pop_id, "reativar": True})["status"], "reativado")
        self.assertIn(pop_id, _ativos(self.db))

    def test_4_obrigatorio_ausente_da_erro_claro(self):
        self.assertIn("titulo", pops.criar(self.db, {"instrucao_sistema": "x"})["erro"])
        self.assertIn("instrucao_sistema", pops.criar(self.db, {"titulo": "x"})["erro"])
        self.assertIn("id", pops.editar(self.db, {"titulo": "x"})["erro"])
        self.assertIn("titulo e/ou instrucao_sistema", pops.editar(self.db, {"id": "x"})["erro"])
        self.assertIn("não encontrado", pops.desativar(self.db, {"id": "nao-existe"})["erro"])
        self.assertIn("gatilho", pops.criar(self.db, {"titulo": "x", "instrucao_sistema": "y", "origem": "gatilhos"})["erro"])
        self.assertEqual(self.db.docs, {})

    def test_tools_estao_no_despacho(self):
        for nome in ("criar_pop", "editar_pop", "desativar_pop", "listar_pops"):
            self.assertIn(nome, hermes_tools._HANDLERS)


if __name__ == "__main__":
    unittest.main()
