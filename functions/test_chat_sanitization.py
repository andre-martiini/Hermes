import unittest
from google.genai import types
from hermes_core_logic import _sanitize_chat_history


class TestChatSanitization(unittest.TestCase):
    def test_empty_history(self):
        self.assertEqual(_sanitize_chat_history([], types), [])

    def test_single_user_message_removed(self):
        # A single user message with no assistant response must be dropped so the new turn can be sent
        raw = [types.Content(role="user", parts=[types.Part(text="Olá")])]
        self.assertEqual(_sanitize_chat_history(raw, types), [])

    def test_single_model_message_removed(self):
        # A leading model message without prior user message must be dropped
        raw = [types.Content(role="model", parts=[types.Part(text="Olá! Como posso ajudar?")])]
        self.assertEqual(_sanitize_chat_history(raw, types), [])

    def test_valid_user_model_pair_preserved(self):
        raw = [
            types.Content(role="user", parts=[types.Part(text="Qual a minha próxima tarefa?")]),
            types.Content(role="model", parts=[types.Part(text="Sua próxima tarefa é X.")]),
        ]
        sanitized = _sanitize_chat_history(raw, types)
        self.assertEqual(len(sanitized), 2)
        self.assertEqual(sanitized[0].role, "user")
        self.assertEqual(sanitized[1].role, "model")
        self.assertEqual(sanitized[0].parts[0].text, "Qual a minha próxima tarefa?")
        self.assertEqual(sanitized[1].parts[0].text, "Sua próxima tarefa é X.")

    def test_trailing_user_message_dropped(self):
        # When a previous turn failed or unclosed user turn exists, drop trailing user turn
        raw = [
            types.Content(role="user", parts=[types.Part(text="Msg 1")]),
            types.Content(role="model", parts=[types.Part(text="Resp 1")]),
            types.Content(role="user", parts=[types.Part(text="Msg 2 (unanswered)")]),
        ]
        sanitized = _sanitize_chat_history(raw, types)
        self.assertEqual(len(sanitized), 2)
        self.assertEqual(sanitized[0].role, "user")
        self.assertEqual(sanitized[1].role, "model")
        self.assertEqual(sanitized[1].parts[0].text, "Resp 1")

    def test_consecutive_same_role_merged(self):
        # Two consecutive user messages get their parts merged
        raw = [
            types.Content(role="user", parts=[types.Part(text="Parte 1")]),
            types.Content(role="user", parts=[types.Part(text="Parte 2")]),
            types.Content(role="model", parts=[types.Part(text="Resposta")]),
        ]
        sanitized = _sanitize_chat_history(raw, types)
        self.assertEqual(len(sanitized), 2)
        self.assertEqual(sanitized[0].role, "user")
        self.assertEqual(len(sanitized[0].parts), 2)
        self.assertEqual(sanitized[0].parts[0].text, "Parte 1")
        self.assertEqual(sanitized[0].parts[1].text, "Parte 2")
        self.assertEqual(sanitized[1].role, "model")

    def test_assistant_role_normalized_to_model(self):
        raw = [
            types.Content(role="user", parts=[types.Part(text="Oi")]),
            types.Content(role="assistant", parts=[types.Part(text="Olá!")]),
        ]
        sanitized = _sanitize_chat_history(raw, types)
        self.assertEqual(len(sanitized), 2)
        self.assertEqual(sanitized[1].role, "model")


if __name__ == "__main__":
    unittest.main()
