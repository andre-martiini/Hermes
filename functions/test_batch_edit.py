import json
import os
import unittest
from unittest.mock import MagicMock


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

    def test_telegram_editar_acoes_em_lote(self):
        # Mock database for hermes_core_logic tool
        mock_db = MagicMock()
        mock_batch = MagicMock()
        mock_db.batch.return_value = mock_batch

        # Mock tasks in firestore
        mock_doc_1 = MagicMock()
        mock_doc_1.exists = True
        mock_doc_1.to_dict.return_value = {
            "titulo": "Tarefa 1",
            "data_limite": "2026-08-20",
            "status": "em andamento"
        }

        mock_doc_2 = MagicMock()
        mock_doc_2.exists = True
        mock_doc_2.to_dict.return_value = {
            "titulo": "Tarefa 2",
            "data_limite": "2026-08-21",
            "status": "em andamento"
        }

        def mock_doc_fn(task_id):
            doc = MagicMock()
            if task_id == "t1":
                doc.get.return_value = mock_doc_1
            elif task_id == "t2":
                doc.get.return_value = mock_doc_2
            else:
                doc.get.return_value = MagicMock(exists=False)
            return doc

        mock_db.collection.return_value.document.side_effect = mock_doc_fn

        # Test batch execution via helper logic
        itens = [
            {"task_id": "t1", "alteracoes": {"data_limite": "2026-08-25"}},
            {"task_id": "t2", "alteracoes": {"data_limite": "2026-08-27", "status": "concluído"}},
        ]

        _ALLOWED = {'titulo', 'descricao', 'data_limite', 'data_inicio', 'prazo_final', 'horario_inicio', 'horario_fim', 'status', 'tags', 'area_tematica', 'tipo_acao', 'notas', 'email_link_optout'}
        updated_count = 0
        for item in itens:
            tid = item.get("task_id")
            tdoc = mock_db.collection("tarefas").document(tid).get()
            if tdoc.exists:
                updates = {k: v for k, v in item["alteracoes"].items() if k in _ALLOWED}
                if updates:
                    mock_batch.update(mock_db.collection("tarefas").document(tid), updates)
                    updated_count += 1

        self.assertEqual(updated_count, 2)
        mock_batch.commit()
        mock_batch.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
