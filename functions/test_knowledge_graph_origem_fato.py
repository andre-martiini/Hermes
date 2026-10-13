"""Testes para P06 sub-entrega 3/N (docs/plano-hermes-autonomo-2026-09-06.md,
pacote P06, passo 8 -- só a metade "nó inédito" do grafo de conhecimento):
`knowledge_graph._dual_pass_find_or_create_node` passa a gravar `origem_fato`
(ver `autonomy/context.py`) ao criar um nó conceitual inédito.

A sub-entrega 1/N (PR #408) e a 2/N (telegram_message_tools.py) cobriram os
dois escritores de FATOS (`main._save_memory_node`); este módulo escreve em
`knowledge_nodes` com uma FORMA DIFERENTE de documento (nó de procedimento,
sem `tipo`/`texto_memoria`), que o passo 1 do pacote deixou como pendência
própria -- é essa pendência que esta sub-entrega resolve, só para a criação
de nó inédito. O caminho de ANEXAR a um nó já existente (que só atualiza
centróide/contadores em `_crystallize_task`, não testado aqui -- fora do
escopo desta sub-entrega) não é tocado por esta mudança e não deve ganhar
nem perder nenhum campo.

Mock de Firestore reaproveitado de `test_outbox_aprovacao._MockDb`, mesmo
padrão de `test_memoria_origem_fato.py` -- sem reimplementar um segundo mock.
`_gemini_client`/`_derive_node_title` são mockados para isolar o campo de
proveniência da chamada real ao Gemini (decisão ANEXAR/CRIAR_NOVO e geração
de título), que não é o escopo desta sub-entrega.
"""

import unittest
from unittest import mock

from test_outbox_aprovacao import _MockDb

import knowledge_graph as kg
from autonomy.context import RESUMO_DERIVADO, origem_fato_de_leitura


def _fake_gemini_client_com_decisao(texto_decisao: str):
    """Fake de `_gemini_client` cujo `generate_content` sempre devolve
    `texto_decisao` -- usado só na etapa de decisão ANEXAR/CRIAR_NOVO
    (dual-pass), nunca na geração de título (mockada separadamente)."""
    client = mock.MagicMock()
    client.models.generate_content.return_value = mock.MagicMock(text=texto_decisao)
    return client


class TestCriaNoIneditoGravaOrigemFato(unittest.TestCase):
    """Caminho sem nenhum nó candidato na mesma área -- pula a decisão da
    LLM e vai direto para a criação de nó inédito."""

    def setUp(self):
        self.db = _MockDb()

    def test_sem_candidatos_grava_origem_fato_resumo_derivado(self):
        with mock.patch.object(kg, "_derive_node_title", return_value="Título Derivado"):
            node_id, peso = kg._dual_pass_find_or_create_node(
                db=self.db,
                api_key="fake-key",
                summary="Resumo do procedimento executado na tarefa.",
                embedding=[0.1, 0.2, 0.3],
                area_tematica="COMPRAS",
                task_id="task-1",
            )

        self.assertEqual(peso, 1.0)
        doc = self.db.collection("knowledge_nodes")._docs[node_id]
        self.assertEqual(doc["origem_fato"], RESUMO_DERIVADO)
        # Regressão: os demais campos do nó continuam gravados como antes.
        self.assertEqual(doc["titulo"], "Título Derivado")
        self.assertEqual(doc["area_tematica"], "COMPRAS")
        self.assertEqual(doc["n_tasks"], 0)

    def test_leitura_do_no_criado_nao_cai_em_legado_desconhecido(self):
        """Elo com `autonomy.context`: um nó criado por esta função nunca
        deveria ser lido como `legacy_unknown` -- ele TEM `origem_fato`."""
        with mock.patch.object(kg, "_derive_node_title", return_value="Título"):
            node_id, _ = kg._dual_pass_find_or_create_node(
                db=self.db,
                api_key="fake-key",
                summary="Outro resumo qualquer.",
                embedding=[0.4, 0.5, 0.6],
                area_tematica="ASSISTENCIA",
                task_id="task-2",
            )

        doc = self.db.collection("knowledge_nodes")._docs[node_id]
        self.assertEqual(origem_fato_de_leitura(doc), RESUMO_DERIVADO)


class TestCriaNoIneditoComCandidatosGravaOrigemFato(unittest.TestCase):
    """Caminho com candidatos na mesma área, mas a LLM decide CRIAR_NOVO --
    o nó inédito criado aqui também precisa gravar a proveniência."""

    def setUp(self):
        self.db = _MockDb()
        # Nó existente na mesma área, candidato a dual-pass.
        self.db.collection("knowledge_nodes").document("existente-1").set({
            "id": "existente-1",
            "titulo": "Procedimento existente",
            "area_tematica": "COMPRAS",
            "embedding": [0.9, 0.9, 0.9],
            "resumo": "Procedimento não relacionado.",
        })

    def test_llm_decide_criar_novo_grava_origem_fato(self):
        with mock.patch.object(
            kg, "_gemini_client", return_value=_fake_gemini_client_com_decisao("CRIAR_NOVO")
        ), mock.patch.object(kg, "_derive_node_title", return_value="Novo Título"):
            node_id, peso = kg._dual_pass_find_or_create_node(
                db=self.db,
                api_key="fake-key",
                summary="Procedimento genuinamente diferente.",
                embedding=[0.1, 0.1, 0.1],
                area_tematica="COMPRAS",
                task_id="task-3",
            )

        self.assertNotEqual(node_id, "existente-1")
        self.assertEqual(peso, 1.0)
        doc = self.db.collection("knowledge_nodes")._docs[node_id]
        self.assertEqual(doc["origem_fato"], RESUMO_DERIVADO)


class TestAnexarANoExistenteNaoTocaOrigemFato(unittest.TestCase):
    """Caminho de ANEXAR: não cria nó novo, não deve gravar nem sobrescrever
    `origem_fato` do nó existente -- a proveniência do nó é a de quando ele
    foi criado, não a de cada tarefa que depois contribuiu para o centróide."""

    def setUp(self):
        self.db = _MockDb()
        self.db.collection("knowledge_nodes").document("existente-1").set({
            "id": "existente-1",
            "titulo": "Procedimento existente",
            "area_tematica": "COMPRAS",
            "embedding": [0.1, 0.1, 0.1],
            "resumo": "Procedimento já conhecido.",
        })

    def test_anexar_nao_grava_origem_fato_no_no_existente(self):
        with mock.patch.object(
            kg,
            "_gemini_client",
            return_value=_fake_gemini_client_com_decisao("ANEXAR:existente-1"),
        ) as gemini_client_mock, mock.patch.object(
            kg, "_derive_node_title"
        ) as derive_title_mock:
            node_id, peso = kg._dual_pass_find_or_create_node(
                db=self.db,
                api_key="fake-key",
                summary="Procedimento parecido com o existente.",
                embedding=[0.1, 0.1, 0.1],
                area_tematica="COMPRAS",
                task_id="task-4",
            )

        self.assertEqual(node_id, "existente-1")
        doc = self.db.collection("knowledge_nodes")._docs["existente-1"]
        self.assertNotIn("origem_fato", doc)
        # Nenhum nó novo foi criado, e o título não precisou ser gerado.
        self.assertEqual(len(self.db.collection("knowledge_nodes")._docs), 1)
        derive_title_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
