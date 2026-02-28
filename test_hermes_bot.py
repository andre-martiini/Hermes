import os
import sys

# Patch environment BEFORE importing main.py from Hermes-Bot
os.environ["GEMINI_API_KEY"] = "mock:key"
os.environ["TELEGRAM_TOKEN"] = "123456:mocktoken"

import unittest
from unittest.mock import patch, MagicMock

# Adiciona diretórios ao sys.path para importar os módulos
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'Hermes-Bot')))

# Mock firebase antes de importar o main.py
mock_db = MagicMock()

with patch('firebase_admin.initialize_app'), patch('firebase_admin.credentials.Certificate'), patch('firebase_admin.firestore.client', return_value=mock_db), patch('google.genai.Client'), patch('telebot.TeleBot.infinity_polling'):
    import main as bot_main

class TestHermesBot(unittest.TestCase):

    def setUp(self):
        # Limpar o mock db para cada teste
        bot_main.db.reset_mock()

    def test_registrar_tarefa_hermes(self):
        # Configurar mock collection
        mock_collection = MagicMock()
        bot_main.db.collection.return_value = mock_collection
        mock_res = (None, MagicMock(id='mock_id_123'))
        mock_collection.add.return_value = mock_res

        # Testar criação sem parâmetros de data e hora
        res = bot_main.registrar_tarefa_hermes("Test Task")

        self.assertIn("registrada com sucesso", res)
        # Verify collection.add was called
        mock_collection.add.assert_called_once()
        args, kwargs = mock_collection.add.call_args
        nova_tarefa = args[0]

        # Verifica se campos defaults foram adicionados
        self.assertEqual(nova_tarefa['origem'], 'telegram_bot')
        self.assertIsNotNone(nova_tarefa['data_limite'])
        self.assertIsNotNone(nova_tarefa['horario_inicio'])

        # Verifica trigger de sync
        bot_main.db.collection.assert_any_call("system")

    def test_atualizar_cronograma_tarefa(self):
        # Configurar mock query stream para encontrar a tarefa
        mock_query = MagicMock()
        bot_main.db.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = mock_query

        mock_doc = MagicMock()
        mock_doc.id = "doc1"
        mock_doc.to_dict.return_value = {"titulo": "Test Task"}

        # Generator para simular stream()
        def mock_stream():
            yield mock_doc

        bot_main.db.collection.return_value.order_by.return_value.limit.return_value.stream = mock_stream

        # Testar atualização
        res = bot_main.atualizar_cronograma_tarefa("Test", "2024-12-31", "10:00")
        self.assertIn("atualizado com sucesso", res)

        # Verifica se update foi chamado na tarefa
        bot_main.db.collection.assert_any_call("tarefas")
        bot_main.db.collection("tarefas").document("doc1").update.assert_called_with({"data_limite": "2024-12-31", "horario_inicio": "10:00"})

        # Verifica trigger de sync
        bot_main.db.collection.assert_any_call("system")

    def test_cancelar_tarefa(self):
        # Configurar mock query stream
        mock_doc = MagicMock()
        mock_doc.id = "doc1"
        mock_doc.to_dict.return_value = {"titulo": "Test Task"}

        def mock_stream():
            yield mock_doc

        bot_main.db.collection.return_value.order_by.return_value.limit.return_value.stream = mock_stream

        # Testar exclusão/cancelamento
        res = bot_main.cancelar_tarefa("Test")
        self.assertIn("cancelada/excluída com sucesso", res)

        bot_main.db.collection("tarefas").document("doc1").update.assert_called_with({"status": "excluído"})
        # Verifica trigger de sync
        bot_main.db.collection.assert_any_call("system")

    def test_diario_de_bordo(self):
        mock_doc = MagicMock()
        mock_doc.to_dict.return_value = {"titulo": "Task1", "notas": "Note1"}

        def mock_stream():
            yield mock_doc

        bot_main.db.collection.return_value.where.return_value.where.return_value.stream = mock_stream

        res = bot_main.diario_de_bordo("2024-01-01")
        self.assertIn("Diário de Bordo (2024-01-01)", res)
        self.assertIn("Task1", res)
        self.assertIn("Note1", res)

    def test_briefing(self):
        def mock_stream_empty():
            yield from []

        bot_main.db.collection.return_value.where.return_value.stream = mock_stream_empty
        bot_main.db.collection.return_value.stream = mock_stream_empty

        res = bot_main.briefing("2024-01-01", "2024-01-01")
        self.assertIn("Briefing para 2024-01-01", res)
        self.assertIn("Nenhuma tarefa pendente", res)
        self.assertIn("Nenhum evento agendado", res)

if __name__ == '__main__':
    unittest.main()