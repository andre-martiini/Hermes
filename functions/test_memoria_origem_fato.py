"""Testes para P06 sub-entrega 1/N (docs/plano-hermes-autonomo-2026-09-06.md,
pacote P06, passo 1): `main._save_memory_node` passa a gravar `origem_fato`
em todo fato novo, e `autonomy.context.origem_fato_de_leitura` normaliza a
leitura de fatos antigos (sem o campo) para `legacy_unknown`.

Mock de Firestore reaproveitado de `test_outbox_aprovacao._MockDb` (mesmo
padrão de `test_telegram_extended.py`), sem reimplementar um segundo mock.
`get_embedding`/`_find_similar_memory_nodes` são mockados para isolar o
campo de proveniência do resto da lógica de similaridade/dedup, que já tem
seu próprio escopo e não foi alterada por esta sub-entrega.
"""

import unittest
from unittest import mock

from test_outbox_aprovacao import _MockDb

import main
from autonomy.context import (
    DECLARACAO_HUMANA,
    FONTE_EXTERNA,
    LEGADO_DESCONHECIDO,
    ORIGENS_FATO_NOVO,
    ORIGENS_FATO_VALIDAS,
    origem_fato_de_leitura,
)


def _patch_embedding_e_similares(candidatos=None):
    """Contexto que isola `_save_memory_node` da geração real de embedding e
    da busca de similares (vector search do Firestore, não suportada pelo
    mock) -- nada aqui testa a lógica de similaridade/dedup, já coberta (ou
    não) em outro lugar; só o campo `origem_fato`."""
    return mock.patch.multiple(
        main,
        get_embedding=mock.DEFAULT,
        _find_similar_memory_nodes=mock.DEFAULT,
    )


class TestSaveMemoryNodeGravaOrigemFato(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()

    def test_fato_novo_grava_declaracao_humana(self):
        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = []
            resultado = main._save_memory_node(
                db=self.db,
                api_key="fake-key",
                fato="André prefere reuniões pela manhã.",
                categoria="preferencia",
            )

        self.assertEqual(resultado["status"], "saved")
        doc = self.db.collection("knowledge_nodes")._docs[resultado["memory_id"]]
        self.assertEqual(doc["origem_fato"], DECLARACAO_HUMANA)

    def test_resolver_conflito_substituir_pelo_novo_grava_declaracao_humana(self):
        self.db.collection("knowledge_nodes").document("mem-1").set({
            "texto_memoria": "fato original",
        })

        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            resultado = main._save_memory_node(
                db=self.db,
                api_key="fake-key",
                fato="fato corrigido pelo usuário",
                categoria="fato_isolado",
                force_update_id="mem-1",
            )

        self.assertEqual(resultado["status"], "updated")
        doc = self.db.collection("knowledge_nodes")._docs["mem-1"]
        self.assertEqual(doc["origem_fato"], DECLARACAO_HUMANA)
        # `_find_similar_memory_nodes` não deveria nem ser chamada no caminho
        # de force_update_id -- ele não busca similares, atualiza o ID dado.
        mocks["_find_similar_memory_nodes"].assert_not_called()

    def test_duplicado_nao_reescreve_origem_fato_do_no_existente(self):
        """O merge de 'duplicado' só atualiza metadados de observação; não
        deve sobrescrever a proveniência original do nó já existente."""
        self.db.collection("knowledge_nodes").document("mem-existente").set({
            "texto_memoria": "fato ja conhecido",
            "tipo": "preferencia",
            "origem_fato": FONTE_EXTERNA,
        })

        with _patch_embedding_e_similares() as mocks:
            mocks["get_embedding"].return_value = [0.1, 0.2, 0.3]
            mocks["_find_similar_memory_nodes"].return_value = [{
                "id": "mem-existente",
                "similarity": 0.999,
                "data": {"texto_memoria": "fato ja conhecido", "tipo": "preferencia"},
            }]
            resultado = main._save_memory_node(
                db=self.db,
                api_key="fake-key",
                fato="fato ja conhecido",
                categoria="preferencia",
            )

        self.assertEqual(resultado["status"], "ignored")
        self.assertEqual(resultado["reason"], "duplicate")
        doc = self.db.collection("knowledge_nodes")._docs["mem-existente"]
        self.assertEqual(doc["origem_fato"], FONTE_EXTERNA)


class TestOrigemFatoDeLeitura(unittest.TestCase):
    def test_documento_sem_campo_e_legado(self):
        self.assertEqual(origem_fato_de_leitura({"texto_memoria": "x"}), LEGADO_DESCONHECIDO)

    def test_documento_none_e_legado(self):
        self.assertEqual(origem_fato_de_leitura(None), LEGADO_DESCONHECIDO)

    def test_documento_vazio_e_legado(self):
        self.assertEqual(origem_fato_de_leitura({}), LEGADO_DESCONHECIDO)

    def test_valor_conhecido_e_preservado(self):
        for origem in ORIGENS_FATO_NOVO:
            with self.subTest(origem=origem):
                self.assertEqual(
                    origem_fato_de_leitura({"origem_fato": origem}), origem
                )

    def test_valor_desconhecido_vira_legado(self):
        self.assertEqual(
            origem_fato_de_leitura({"origem_fato": "categoria_inventada_no_futuro"}),
            LEGADO_DESCONHECIDO,
        )

    def test_legado_desconhecido_esta_entre_os_validos(self):
        self.assertIn(LEGADO_DESCONHECIDO, ORIGENS_FATO_VALIDAS)
        for origem in ORIGENS_FATO_NOVO:
            self.assertIn(origem, ORIGENS_FATO_VALIDAS)


if __name__ == "__main__":
    unittest.main()
