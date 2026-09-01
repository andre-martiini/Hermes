import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, '.')

from inbox_pendentes import coletar


class Doc:
    def __init__(self, doc_id, data):
        self.id, self.data, self.exists = doc_id, data, data is not None
    def to_dict(self): return dict(self.data or {})
    def get(self): return self


class Query:
    def __init__(self, docs): self.docs = docs
    def stream(self): return list(self.docs)
    def document(self, wanted):
        return next((d for d in self.docs if d.id == wanted), Doc(wanted, None))


class Db:
    def __init__(self, collections): self.collections = collections
    def collection(self, name):
        return Query([Doc(key, value) for key, value in self.collections.get(name, {}).items()])


class InboxPendentesTest(unittest.TestCase):
    def test_lista_tres_recebidas_ordem_e_exclui_enviada_pausada(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['a', 'b', 'c', 'd', 'e']}}},
            'perfil_pessoas': {'a': {'nome': 'Gabriela', 'whatsapp_chat_id': 'a'}},
            'tarefas': {},
            'email_action_suggestions': {},
            'inbox_pendentes': {
                'a': {'tipo': 'whatsapp', 'chat_id': 'a', 'desde': '2026-09-01T06:00:00+00:00', 'trecho': 'A'},
                'b': {'tipo': 'whatsapp', 'chat_id': 'b', 'chat_name': 'Ezequiel', 'desde': '2026-09-01T08:00:00+00:00', 'trecho': 'B'},
                'c': {'tipo': 'whatsapp', 'chat_id': 'c', 'chat_name': 'Marcelo', 'desde': '2026-09-01T10:00:00+00:00', 'trecho': 'C'},
                'd': {'tipo': 'whatsapp', 'chat_id': 'd', 'ultima_de_andre': True, 'desde': '2026-09-01T01:00:00+00:00'},
                'e': {'tipo': 'whatsapp', 'chat_id': 'e', 'desde': '2026-09-01T00:00:00+00:00', 'pausada_ate': '2026-09-02T00:00:00+00:00'},
            },
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual([x['contato'] for x in result['itens']], ['Gabriela', 'Ezequiel', 'Marcelo'])

    def test_grupo_sem_acao_ativa_e_excluido_na_regra_conservadora(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['g']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {},
            'tarefas': {},
            'inbox_pendentes': {'g': {'tipo': 'whatsapp', 'chat_id': 'g', 'is_group': True,
                'desde': '2026-09-01T10:00:00+00:00'}},
        })
        self.assertEqual(coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))['itens'], [])


if __name__ == '__main__':
    unittest.main()
