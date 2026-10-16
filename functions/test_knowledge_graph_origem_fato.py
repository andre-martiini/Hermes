"""Testes para P06 sub-entrega 4/N (docs/plano-hermes-autonomo-2026-09-06.md,
pacote P06, passo 8): os dois pontos de escrita de `knowledge_nodes` em
`knowledge_graph.py` (criação em `_dual_pass_find_or_create_node`,
atualização em `_crystallize_task`) passam a gravar
`origem_fato=RESUMO_DERIVADO` -- quarto chamador de `autonomy.context`,
primeiro que não passa por `main._save_memory_node`/`salvar_memoria_global`.

Mock de Firestore reaproveitado de `test_outbox_aprovacao._MockDb` (mesmo
padrão de `test_memoria_origem_fato.py`), sem reimplementar um segundo mock.
Toda chamada real a Gemini (decisão do Dual-Pass, título do nó, resumo do
diário, embedding) é mockada -- nada aqui testa essa lógica, só o campo de
proveniência gravado nos dois pontos de escrita.

Achado real da 1a rodada de revisão adversarial independente desta
sub-entrega (confirmado por mutation test): a asserção de `origem_fato` que
a 1a versão deste arquivo tinha em
`TestCrystallizeTaskGravaOrigemFato.test_atualiza_no_existente_grava_origem_resumo_derivado`
era um falso positivo -- o `setUp` daquele teste já partia de um nó com
`origem_fato=RESUMO_DERIVADO`, e o mock de `.update()` faz merge (igual ao
Firestore real), então o valor permanecia correto mesmo removendo a linha
`"origem_fato": RESUMO_DERIVADO,` do ponto de escrita de atualização em
`_crystallize_task`. Corrigido removendo essa asserção redundante (o teste
passou a cobrir só os demais campos que o `.update()` grava) -- a cobertura
real do ponto de ATUALIZAÇÃO vem de
`test_backfill_lazy_no_sem_origem_fato_previo_e_atualizado_para_resumo_derivado`,
que parte de um nó SEM o campo e por isso é sensível à mutação.
"""

import unittest
from unittest import mock

from test_outbox_aprovacao import _MockDb

import knowledge_graph as kg
from autonomy.context import RESUMO_DERIVADO


class TestDualPassFindOrCreateNodeGravaOrigemFato(unittest.TestCase):
    """Criação de nó inédito (sem candidatos na área, ou LLM decide
    CRIAR_NOVO) -- o único ponto de escrita de um nó novo."""

    def setUp(self):
        self.db = _MockDb()

    def test_sem_candidatos_na_area_cria_no_com_origem_resumo_derivado(self):
        with mock.patch.object(kg, "_derive_node_title", return_value="Título Teste"):
            node_id, peso = kg._dual_pass_find_or_create_node(
                self.db,
                api_key="fake-key",
                summary="Resumo do procedimento executado.",
                embedding=[0.1, 0.2, 0.3],
                area_tematica="JURIDICO",
                task_id="tarefa-1",
            )

        self.assertEqual(peso, 1.0)
        doc = self.db.collection("knowledge_nodes")._docs[node_id]
        self.assertEqual(doc["origem_fato"], RESUMO_DERIVADO)

    def test_llm_decide_criar_novo_mesmo_com_candidatos_grava_origem_resumo_derivado(self):
        # Um nó existente na mesma área, com embedding, para popular
        # top_candidates e exercitar o prompt de decisão do Dual-Pass.
        self.db.collection("knowledge_nodes").document("no-existente").set({
            "titulo": "Procedimento existente",
            "area_tematica": "JURIDICO",
            "resumo": "algo",
            "embedding": [0.9, 0.0, 0.0],
        })

        fake_response = mock.Mock()
        fake_response.text = "CRIAR_NOVO"
        fake_client = mock.Mock()
        fake_client.models.generate_content.return_value = fake_response

        with mock.patch.object(kg, "_gemini_client", return_value=fake_client), \
             mock.patch.object(kg, "_derive_node_title", return_value="Título Teste"):
            node_id, peso = kg._dual_pass_find_or_create_node(
                self.db,
                api_key="fake-key",
                summary="Resumo de um procedimento bem diferente.",
                embedding=[0.1, 0.2, 0.3],
                area_tematica="JURIDICO",
                task_id="tarefa-2",
            )

        self.assertNotEqual(node_id, "no-existente")
        doc = self.db.collection("knowledge_nodes")._docs[node_id]
        self.assertEqual(doc["origem_fato"], RESUMO_DERIVADO)

    def test_llm_decide_anexar_nao_escreve_nada_e_nao_toca_origem_fato_existente(self):
        """Quando o Dual-Pass decide ANEXAR a um nó já existente, nenhuma
        escrita nova acontece aqui -- `_crystallize_task` é quem atualiza o
        nó (coberto na classe abaixo). Uma proveniência já gravada no nó
        existente (ex.: por um backfill futuro) não pode ser tocada por este
        caminho."""
        self.db.collection("knowledge_nodes").document("no-existente").set({
            "titulo": "Procedimento existente",
            "area_tematica": "JURIDICO",
            "resumo": "algo",
            "embedding": [0.1, 0.2, 0.3],
            "origem_fato": RESUMO_DERIVADO,
        })

        fake_response = mock.Mock()
        fake_response.text = "ANEXAR:no-existente"
        fake_client = mock.Mock()
        fake_client.models.generate_content.return_value = fake_response

        with mock.patch.object(kg, "_gemini_client", return_value=fake_client):
            node_id, peso = kg._dual_pass_find_or_create_node(
                self.db,
                api_key="fake-key",
                summary="Resumo parecido com o procedimento existente.",
                embedding=[0.1, 0.2, 0.3],
                area_tematica="JURIDICO",
                task_id="tarefa-3",
            )

        self.assertEqual(node_id, "no-existente")
        doc = self.db.collection("knowledge_nodes")._docs["no-existente"]
        self.assertEqual(doc["origem_fato"], RESUMO_DERIVADO)
        self.assertNotIn("data_criacao", doc)  # confirma que não foi recriado


class TestCrystallizeTaskGravaOrigemFato(unittest.TestCase):
    """Atualização de um nó já existente (fluxo completo via
    `_crystallize_task`, chamada tanto pelo trigger `on_tarefa_concluida_kg`
    quanto por `crystallize_task_manual`)."""

    def setUp(self):
        self.db = _MockDb()
        self.task_data = {
            "titulo": "Tarefa concluída",
            "area_tematica": "JURIDICO",
            "data_conclusao": "2026-10-16",
        }
        self.db.collection("tarefas").document("tarefa-existente").set(dict(self.task_data))

    def _patches(self):
        return mock.patch.multiple(
            kg,
            _build_clean_diary=mock.DEFAULT,
            _gemini_client=mock.DEFAULT,
            _get_embedding=mock.DEFAULT,
            _dual_pass_find_or_create_node=mock.DEFAULT,
            _aggregate_artefatos=mock.DEFAULT,
        )

    def test_atualiza_no_existente_mantem_demais_campos_corretos(self):
        """Cobre os demais campos que `node_ref.update(...)` grava (n_tasks,
        task_ids, resumo) -- NÃO a proveniência: como este `setUp` já parte
        de um nó com `origem_fato=RESUMO_DERIVADO`, uma asserção de
        `origem_fato` aqui seria um falso positivo (passaria mesmo sem a
        linha `"origem_fato": RESUMO_DERIVADO,` existir no ponto de
        atualização, já que o mock de `.update()` faz merge e o valor
        inicial já é o esperado -- achado real da 1a rodada de revisão
        adversarial desta sub-entrega). A cobertura real de que o ponto de
        ATUALIZAÇÃO grava `origem_fato` vem do teste de backfill abaixo, que
        parte de um nó SEM o campo."""
        self.db.collection("knowledge_nodes").document("no-existente").set({
            "titulo": "Procedimento existente",
            "embedding": [0.1, 0.2, 0.3],
            "n_tasks": 1,
            "task_ids": ["tarefa-anterior"],
            "resumo": "resumo antigo",
            "origem_fato": RESUMO_DERIVADO,
        })

        fake_summary_response = mock.Mock()
        fake_summary_response.text = "Resumo técnico do procedimento."
        fake_client = mock.Mock()
        fake_client.models.generate_content.return_value = fake_summary_response

        with self._patches() as mocks:
            mocks["_build_clean_diary"].return_value = "diário limpo"
            mocks["_gemini_client"].return_value = fake_client
            mocks["_get_embedding"].return_value = [0.4, 0.5, 0.6]
            mocks["_dual_pass_find_or_create_node"].return_value = ("no-existente", 0.9)
            mocks["_aggregate_artefatos"].return_value = []

            kg._crystallize_task("tarefa-existente", self.task_data, self.db, api_key="fake-key")

        doc = self.db.collection("knowledge_nodes")._docs["no-existente"]
        self.assertEqual(doc["n_tasks"], 2)
        self.assertIn("tarefa-existente", doc["task_ids"])
        self.assertEqual(doc["resumo"], "Resumo técnico do procedimento.")

    def test_backfill_lazy_no_sem_origem_fato_previo_e_atualizado_para_resumo_derivado(self):
        """Nó criado ANTES desta sub-entrega (sem `origem_fato` nenhum) --
        `origem_fato_de_leitura` classificaria como `legacy_unknown` até
        aqui. Ao ser cristalizado de novo (nova tarefa no mesmo nó), passa a
        ter `origem_fato=RESUMO_DERIVADO` sem nenhuma migração/backfill
        script separado."""
        self.db.collection("knowledge_nodes").document("no-legado").set({
            "titulo": "Procedimento legado",
            "embedding": [0.1, 0.2, 0.3],
            "n_tasks": 3,
            "task_ids": ["t1", "t2", "t3"],
            "resumo": "resumo antigo",
            # Sem origem_fato -- simula um nó gravado antes desta sub-entrega.
        })

        fake_summary_response = mock.Mock()
        fake_summary_response.text = "Resumo técnico do procedimento."
        fake_client = mock.Mock()
        fake_client.models.generate_content.return_value = fake_summary_response

        with self._patches() as mocks:
            mocks["_build_clean_diary"].return_value = "diário limpo"
            mocks["_gemini_client"].return_value = fake_client
            mocks["_get_embedding"].return_value = [0.4, 0.5, 0.6]
            mocks["_dual_pass_find_or_create_node"].return_value = ("no-legado", 0.9)
            mocks["_aggregate_artefatos"].return_value = []

            kg._crystallize_task("tarefa-existente", self.task_data, self.db, api_key="fake-key")

        doc = self.db.collection("knowledge_nodes")._docs["no-legado"]
        self.assertEqual(doc["origem_fato"], RESUMO_DERIVADO)


if __name__ == "__main__":
    unittest.main()
