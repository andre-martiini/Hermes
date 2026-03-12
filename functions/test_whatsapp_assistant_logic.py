import unittest
from datetime import datetime, timezone

from whatsapp_assistant_logic import (
    build_chat_candidates,
    build_whatsapp_context,
    resolve_search_keywords,
    resolve_time_scope,
    select_relevant_messages,
    should_prompt_for_chat_confirmation,
)


class TestWhatsAppAssistantLogic(unittest.TestCase):
    def test_follow_up_reuses_previous_keywords(self):
        keywords = resolve_search_keywords('E hoje?', ['obra', 'pendencia'])
        self.assertEqual(keywords, ['obra', 'pendencia'])

    def test_chat_confirmation_is_required_when_candidates_are_too_close(self):
        candidates = [
            {'chatId': '1', 'chatName': 'Obra Campus', 'score': 0.63, 'isGroup': True},
            {'chatId': '2', 'chatName': 'Obra Centro', 'score': 0.59, 'isGroup': True},
        ]
        self.assertTrue(should_prompt_for_chat_confirmation(candidates))

    def test_select_relevant_messages_prioritizes_matching_content_and_keeps_neighbors(self):
        items = [
            {
                'id': 'msg-1',
                'timestamp': '2026-03-12T09:00:00.000Z',
                'content': 'Bom dia, equipe.',
                'chat_name': 'Obra Campus',
                'contact_name': 'Ana',
                'author_name': 'Ana',
                'links': [],
                'message_type': 'text',
            },
            {
                'id': 'msg-2',
                'timestamp': '2026-03-12T09:02:00.000Z',
                'content': 'A pendencia da obra ficou para hoje.',
                'chat_name': 'Obra Campus',
                'contact_name': 'Bruno',
                'author_name': 'Bruno',
                'links': [],
                'message_type': 'text',
            },
            {
                'id': 'msg-3',
                'timestamp': '2026-03-12T09:04:00.000Z',
                'content': 'Vou enviar o anexo em seguida.',
                'chat_name': 'Obra Campus',
                'contact_name': 'Bruno',
                'author_name': 'Bruno',
                'links': [],
                'message_type': 'text',
            },
        ]

        selected = select_relevant_messages(items, ['pendencia', 'obra'], 'Mostre a pendencia da obra')
        self.assertEqual([item['id'] for item in selected], ['msg-1', 'msg-2', 'msg-3'])

    def test_build_context_compacts_messages_and_exposes_attachment_refs(self):
        context_block, attachments, message_ids = build_whatsapp_context([
            {
                'id': 'msg-4',
                'timestamp': '2026-03-12T10:00:00.000Z',
                'content': 'Segue o relatorio.',
                'transcription_text': '',
                'chat_name': 'Obra Campus',
                'chat_id': 'chat-1',
                'contact_name': 'Carla',
                'author_name': 'Carla',
                'links': ['https://example.com'],
                'message_type': 'document',
                'media': {
                    'url': 'https://signed.example/file.pdf',
                    'fileName': 'relatorio.pdf',
                    'mimeType': 'application/pdf',
                },
            }
        ])

        self.assertIn('anexo: ARQ-1 (relatorio.pdf, application/pdf)', context_block)
        self.assertNotIn('https://signed.example', context_block)
        self.assertEqual(attachments[0]['referenceId'], 'ARQ-1')
        self.assertEqual(message_ids, ['msg-4'])

    def test_time_scope_understands_today(self):
        scope = resolve_time_scope('O que aconteceu hoje?', now=datetime(2026, 3, 12, 15, 0, tzinfo=timezone.utc))
        self.assertIsNotNone(scope)
        self.assertEqual(scope['label'], 'hoje')

    def test_build_chat_candidates_ranks_best_match_first(self):
        items = [
            {'chat_id': '1', 'chat_name': 'Obra Campus', 'is_group': True},
            {'chat_id': '2', 'chat_name': 'Compras Gerais', 'is_group': True},
            {'chat_id': '3', 'chat_name': 'Obra Centro', 'is_group': True},
        ]
        candidates = build_chat_candidates(items, 'obra')
        self.assertEqual(candidates[0]['chatName'], 'Obra Campus')


if __name__ == '__main__':
    unittest.main()
