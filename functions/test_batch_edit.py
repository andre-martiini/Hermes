import ast
import inspect
import json
import os
import unittest
from unittest.mock import MagicMock

from firebase_admin import firestore

import telegram_message_tools


class TestBatchEdit(unittest.TestCase):
    def test_schema_validity(self):
        schema_path = os.path.join(os.path.dirname(__file__), "tools", "schemas", "preparar_edicao_em_lote.json")
        self.assertTrue(os.path.exists(schema_path), f"Schema file not found at {schema_path}")
        with open(schema_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("name"), "preparar_edicao_em_lote")
        self.assertIn("itens", data.get("parameters", {}).get("properties", {}))
        self.assertIn("justificativa", data.get("parameters", {}).get("properties", {}))

    def test_registry_contains_batch_edit(self):
        from tools.registry import _CATALOG
        self.assertIn("preparar_edicao_em_lote", _CATALOG)


class TestTelegramEditarAcoesEmLoteReal(unittest.TestCase):
    """Achado da 4ª rodada de revisão adversarial (23/09/2026): o teste
    anterior (`test_telegram_editar_acoes_em_lote`) nunca chamava
    `telegram_message_tools.editar_acoes_em_lote` de verdade -- reimplementava
    um laço próprio, hand-rolled, e testava ISSO. Passaria sem alterar nada
    mesmo que a closure real não checasse status nenhum (que era exatamente
    o caso: era uma QUINTA cópia da validação de edição de ação, sem bloqueio
    de 'excluído', achada só nesta rodada).

    Extrai e executa o corpo REAL da closure via AST + exec, isolando só o
    que ela de fato captura (`db`, `json`, `firestore`) -- mesma técnica já
    usada em test_tool_schemas.py::TestSecretarioTelegramExecucao para as
    closures do modo secretário.
    """

    def setUp(self):
        self.db = MagicMock()
        arvore = ast.parse(inspect.getsource(telegram_message_tools.build_telegram_tool_closures))
        no = next(
            n for n in arvore.body[0].body
            if isinstance(n, ast.FunctionDef) and n.name == "editar_acoes_em_lote"
        )
        modulo = ast.Module(body=[no], type_ignores=[])
        namespace = {"db": self.db, "json": json, "firestore": firestore}
        exec(compile(ast.fix_missing_locations(modulo), "<closure-editar-acoes-em-lote-real>", "exec"), namespace)
        self.editar_acoes_em_lote = namespace["editar_acoes_em_lote"]

    def _mockar_tarefas(self, tarefas: dict):
        """`tarefas`: task_id -> dict de dados (ou None para 'não existe')."""
        def mock_doc_fn(task_id):
            doc = MagicMock()
            dados = tarefas.get(task_id)
            if dados is None:
                doc.get.return_value = MagicMock(exists=False)
            else:
                snap = MagicMock(exists=True)
                snap.to_dict.return_value = dados
                doc.get.return_value = snap
            return doc

        self.db.collection.return_value.document.side_effect = mock_doc_fn

    def test_duas_tarefas_em_andamento_sao_atualizadas(self):
        self._mockar_tarefas({
            "t1": {"titulo": "Tarefa 1", "data_limite": "2026-08-20", "status": "em andamento"},
            "t2": {"titulo": "Tarefa 2", "data_limite": "2026-08-21", "status": "em andamento"},
        })
        itens = [
            {"task_id": "t1", "alteracoes": {"data_limite": "2026-08-25"}},
            {"task_id": "t2", "alteracoes": {"data_limite": "2026-08-27", "status": "concluído"}},
        ]
        r = self.editar_acoes_em_lote(itens=itens)
        self.assertTrue(r.startswith("Sucesso!"), r)
        self.assertIn("2 ações atualizadas", r)
        self.db.batch.return_value.commit.assert_called_once()

    def test_excluida_e_recusada_e_nao_e_contada(self):
        """Achado central desta rodada: 'excluído' dispara exclusão real do
        documento e do evento do Calendar na próxima sincronização
        (sync_google_tasks_push, main.py) -- editar outro campo sem reabrir
        é inútil na melhor das hipóteses. As outras 4 cópias desta mesma
        validação (editar_acao, confirmar_edicao_acao, editar_acoes_em_lote
        do conector MCP, preparar_edicao_acao x2) já bloqueiam isso; esta
        closure do Telegram não bloqueava nada."""
        self._mockar_tarefas({
            "t1": {"titulo": "Tarefa excluída", "status": "excluído"},
        })
        r = self.editar_acoes_em_lote(itens=[{"task_id": "t1", "alteracoes": {"titulo": "Novo título"}}])
        self.assertEqual(r, "Nenhuma ação pôde ser atualizada com os dados fornecidos.")
        self.db.batch.return_value.update.assert_not_called()

    def test_excluida_reabrindo_com_sinonimo_e_permitido(self):
        """Prova que a troca da normalização inline (capenga, sem sinônimos
        nem dobra de acento/maiúsculas) pela canônica
        (tools.hermes_tools._normalizar_status_acao) funciona de ponta a
        ponta -- "reabrir" não era reconhecido nem pela normalização antiga
        nem pelo bloqueio (que não existia)."""
        self._mockar_tarefas({
            "t1": {"titulo": "Tarefa excluída por engano", "status": "excluído"},
        })
        r = self.editar_acoes_em_lote(itens=[{"task_id": "t1", "alteracoes": {"status": "reabrir"}}])
        self.assertTrue(r.startswith("Sucesso!"), r)
        payload = self.db.batch.return_value.update.call_args[0][1]
        self.assertEqual(payload["status"], "em andamento")

    def test_tarefa_inexistente_e_pulada_sem_quebrar_o_lote(self):
        self._mockar_tarefas({
            "t1": {"titulo": "Tarefa 1", "status": "em andamento"},
        })
        r = self.editar_acoes_em_lote(itens=[
            {"task_id": "t1", "alteracoes": {"titulo": "Novo"}},
            {"task_id": "t-fantasma", "alteracoes": {"titulo": "Novo"}},
        ])
        self.assertTrue(r.startswith("Sucesso!"), r)
        self.assertIn("1 ações atualizadas", r)


if __name__ == "__main__":
    unittest.main()
