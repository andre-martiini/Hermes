import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, '.')

from inbox_pendentes import atualizar_whatsapp_em_lote, backfill_whatsapp_inicial, coletar


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

    def test_status_stand_by_alias_mantem_grupo_vinculado(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['g']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'stand by', 'whatsapp_vinculos': [{'chat_id': 'g'}]}},
            'inbox_pendentes': {'g': {'tipo': 'whatsapp', 'chat_id': 'g', 'is_group': True,
                'desde': '2026-09-01T10:00:00+00:00'}},
        })
        self.assertEqual([x['contato'] for x in coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))['itens']], ['g'])

    def test_email_respondido_fecha_toda_a_thread(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': []}}},
            'perfil_pessoas': {},
            'tarefas': {'t': {'titulo': 'Ação', 'status': 'em andamento'}},
            'inbox_pendentes': {},
            'email_action_suggestions': {
                'old': {'canal': 'email', 'status': 'applied', 'task_id': 't', 'gmail_thread_id': 'thread',
                        'internal_date': '2026-09-01T08:00:00+00:00', 'sender': 'proad'},
                'new': {'canal': 'email', 'status': 'applied', 'task_id': 't', 'gmail_thread_id': 'thread',
                        'internal_date': '2026-09-01T10:00:00+00:00', 'ultima_mensagem_de_andre': True, 'sender': 'proad'},
            },
        })
        self.assertEqual(coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))['itens'], [])

    def test_grupo_com_resposta_a_andre_entra_sem_acao(self):
        db = Db({
            'system': {'settings': {'whatsapp_ingest': {'chats_allowlist': ['g']}}},
            'perfil_pessoas': {}, 'email_action_suggestions': {}, 'tarefas': {},
            'inbox_pendentes': {'g': {'tipo': 'whatsapp', 'chat_id': 'g', 'chat_name': 'Equipe',
                'is_group': True, 'quoted_msg_id': 'old', 'quoted_from_me': True,
                'desde': '2026-09-01T10:00:00+00:00'}},
        })
        result = coletar(db, datetime(2026, 9, 1, 12, tzinfo=timezone.utc))
        self.assertEqual([x['contato'] for x in result['itens']], ['Equipe'])


class _MemorySnap:
    def __init__(self, ref): self.ref, self.exists = ref, ref.data is not None
    def to_dict(self): return dict(self.ref.data or {})


class _MemoryRef:
    def __init__(self, ident, data=None): self.id, self.data, self.set_calls = ident, data, []
    def get(self): return _MemorySnap(self)
    def set(self, data, merge=False): self.set_calls.append((data, merge)); self.data = {**(self.data or {}), **data} if merge else data


class _MemoryCollection:
    def __init__(self): self.refs = {}
    def document(self, ident): return self.refs.setdefault(ident, _MemoryRef(ident))


class _Batch:
    def __init__(self): self.ops = []; self.committed = False
    def set(self, ref, data, merge=False): self.ops.append((ref, data, merge))
    def commit(self):
        self.committed = True
        for ref, data, merge in self.ops: ref.set(data, merge=merge)


class _MemoryDb:
    def __init__(self): self.inbox, self.batches = _MemoryCollection(), []
    def collection(self, name):
        assert name == 'inbox_pendentes'
        return self.inbox
    def batch(self):
        batch = _Batch(); self.batches.append(batch); return batch


class InboxBatchTest(unittest.TestCase):
    def test_lote_colapsa_por_chat_e_grava_em_batch(self):
        db = _MemoryDb()
        count = atualizar_whatsapp_em_lote(db, [
            {'chat_id': 'a', 'timestamp': '2026-09-01T08:00:00+00:00', 'content': 'antiga'},
            {'chat_id': 'a', 'timestamp': '2026-09-01T10:00:00+00:00', 'content': 'nova'},
            {'chat_id': 'b', 'timestamp': '2026-09-01T09:00:00+00:00', 'content': 'outra'},
        ])
        self.assertEqual(count, 2)
        self.assertEqual(len(db.batches), 1)
        self.assertEqual(len(db.batches[0].ops), 2)
        self.assertEqual(db.inbox.document('wa_YQ').data['trecho'], 'nova')


class _Chain:
    def __init__(self, docs): self.docs = docs
    def order_by(self, *args, **kwargs): return self
    def start_after(self, *args, **kwargs): return self
    def where(self, *args, **kwargs): return self
    def limit(self, *args, **kwargs): return self
    def stream(self): return list(self.docs)


class _BackfillDb:
    def __init__(self):
        self.marker = _MemoryRef('inbox_pendentes_backfill')
        self.chats = _Chain([Doc('chat-a', {'chat_id': 'a'})])
        self.messages = _Chain([Doc('m1', {'chat_id': 'a', 'timestamp': '2026-09-01T10:00:00+00:00'})])
    def collection(self, name):
        if name == 'system': return type('System', (), {'document': lambda _, ident: self.marker})()
        if name == 'whatsapp_chats': return self.chats
        if name == 'whatsapp_messages': return self.messages
        raise AssertionError(name)


class InboxBackfillTest(unittest.TestCase):
    def test_backfill_usa_ultima_mensagem_de_cada_chat_e_marca_progresso(self):
        from unittest import mock
        db = _BackfillDb()
        with mock.patch('inbox_pendentes.atualizar_whatsapp_em_lote') as update:
            self.assertTrue(backfill_whatsapp_inicial(db))
        self.assertEqual(update.call_args.args[1], [{'chat_id': 'a', 'timestamp': '2026-09-01T10:00:00+00:00'}])
        self.assertTrue(db.marker.data['completed_at'])


if __name__ == '__main__':
    unittest.main()
