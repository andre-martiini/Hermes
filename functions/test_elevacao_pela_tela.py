"""Aceitar/Descartar uma elevação pelo Painel do dia.

O que protege: aceitar cria a ação E a vincula ao objetivo (os dois passos do
agente), descartar é `nunca`, e uma ação que não nasce não deixa a sugestão
decidida (não dá para repetir a decisão).
"""

import unittest
from unittest import mock

import deteccao_subproduto as ds
import elevacao_pela_tela as ept
from test_outbox_aprovacao import _MockDb

HOJE = "2026-10-27"


def _db():
    db = _MockDb()
    db.collection(ds.COL_ELEVACOES).document("s1").set({
        "status": ds.STATUS_PENDENTE, "task_id": "origem", "titulo_acao": "Workshop de IA",
        "objetivo_id": "obj1", "nome_objetivo": "Disseminar IA",
    })
    db.collection("tarefas").document("origem").set({"area_tematica": "EVENTOS"})
    return db


def _decidir_falso(db, sugestao_id, decisao, hoje, aplicar=None):
    """Mesma devolução de `ds.decidir` sem o Firestore transacional (testado em outro arquivo)."""
    ref = db.collection(ds.COL_ELEVACOES).document(sugestao_id)
    dados = ref.get().to_dict()
    if dados["status"] != ds.STATUS_PENDENTE:
        return {"ok": False, "erro": f"Sugestao ja estava como '{dados['status']}'."}
    ref.update({"status": ds.DECISOES[decisao], "decidida_em": hoje})
    res = {"ok": True, "status": ds.DECISOES[decisao], "sugestao_id": sugestao_id}
    if decisao == "aceitar":
        res["rascunho_da_acao"] = {"titulo": "Kit aberto do workshop", "descricao": "Elevacao da acao X"}
        res["vincular_depois"] = {"tool": "editar_acao", "estrategia_objetivo_id": dados["objetivo_id"]}
    return res


class TestDecidirPelaTela(unittest.TestCase):

    def setUp(self):
        self.db = _db()
        self.criadas, self.vinculos = [], []
        p = mock.patch.object(ds, "decidir", _decidir_falso)
        p.start()
        self.addCleanup(p.stop)

    def _criar(self, resposta="OK|nova-acao"):
        def criar(args):
            self.criadas.append(args)
            if isinstance(resposta, Exception):
                raise resposta
            return resposta
        return criar

    def _vincular(self, resposta=None):
        def vincular(task_id, objetivo_id):
            self.vinculos.append((task_id, objetivo_id))
            return resposta if resposta is not None else {"aplicado": True}
        return vincular

    def _decidir(self, decisao, **kw):
        return ept.decidir_pela_tela(self.db, "s1", decisao, HOJE,
                                     criar_acao=kw.get("criar") or self._criar(),
                                     vincular=kw.get("vincular") or self._vincular())

    def _status(self):
        return self.db.collection(ds.COL_ELEVACOES)._docs["s1"]["status"]

    def test_aceitar_cria_a_acao_com_o_rascunho_e_vincula_ao_objetivo(self):
        res = self._decidir("aceitar")
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["task_id"], "nova-acao")
        self.assertEqual(self._status(), ds.STATUS_ACEITA)
        self.assertEqual(self.criadas, [{
            "titulo": "Kit aberto do workshop", "descricao": "Elevacao da acao X",
            "area_tematica": "EVENTOS", "data_limite": HOJE}])
        self.assertEqual(self.vinculos, [("nova-acao", "obj1")])

    def test_a_acao_criada_nao_ganha_horario(self):
        self._decidir("aceitar")
        self.assertNotIn("horario_inicio", self.criadas[0])
        self.assertNotIn("horario_fim", self.criadas[0])

    def test_area_cai_em_geral_sem_acao_de_origem(self):
        self.db.collection("tarefas")._docs.clear()
        self._decidir("aceitar")
        self.assertEqual(self.criadas[0]["area_tematica"], "GERAL")

    def test_descartar_e_nunca_e_nao_cria_acao(self):
        res = self._decidir("descartar")
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], ds.STATUS_NUNCA)
        self.assertEqual(self._status(), ds.STATUS_NUNCA)
        self.assertEqual(self.criadas, [])
        self.assertEqual(self.vinculos, [])

    def test_decisao_invalida_nao_toca_em_nada(self):
        for d in ("adiar", "nunca", "", None):
            res = self._decidir(d)
            self.assertFalse(res["ok"], d)
        self.assertEqual(self._status(), ds.STATUS_PENDENTE)

    def test_acao_que_nao_nasce_devolve_a_sugestao_a_pendente(self):
        res = self._decidir("aceitar", criar=self._criar("ERRO|area invalida"))
        self.assertFalse(res["ok"])
        self.assertIn("area invalida", res["erro"])
        self.assertIn("continua pendente", res["erro"])
        self.assertEqual(self._status(), ds.STATUS_PENDENTE)
        self.assertEqual(self.vinculos, [])

    def test_excecao_ao_criar_tambem_devolve_a_pendente(self):
        res = self._decidir("aceitar", criar=self._criar(RuntimeError("boom")))
        self.assertFalse(res["ok"])
        self.assertEqual(self._status(), ds.STATUS_PENDENTE)

    def test_falha_no_vinculo_mantem_aceita_e_avisa_sem_criar_de_novo(self):
        res = self._decidir("aceitar", vincular=self._vincular({"erro": "sem permissao"}))
        self.assertTrue(res["ok"])
        self.assertIn("vinculo", res["aviso"])
        self.assertEqual(res["task_id"], "nova-acao")
        self.assertEqual(self._status(), ds.STATUS_ACEITA)
        self.assertEqual(len(self.criadas), 1)

    def test_sugestao_ja_decidida_nao_cria_acao(self):
        self._decidir("descartar")
        res = self._decidir("aceitar")
        self.assertFalse(res["ok"])
        self.assertEqual(self.criadas, [])

    def test_sem_id(self):
        res = ept.decidir_pela_tela(self.db, "", "aceitar", HOJE, criar_acao=self._criar(), vincular=self._vincular())
        self.assertFalse(res["ok"])


if __name__ == "__main__":
    unittest.main()
