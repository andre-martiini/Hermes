import sys
import unittest

sys.path.insert(0, '.')

from email_action_linker import atualizar_direcao_emails_aplicados


class _Req:
    def __init__(self, value): self.value = value
    def execute(self): return self.value


class _Ref:
    def __init__(self, data): self.data, self.set_calls = data, []
    def set(self, data, merge=False): self.set_calls.append((data, merge)); self.data.update(data)


class _Doc:
    def __init__(self, ident, data): self.id, self.reference = ident, _Ref(data)
    def to_dict(self): return dict(self.reference.data)


class _Suggestions:
    def __init__(self, docs): self.docs = docs
    def where(self, *args): return self
    def limit(self, _): return self
    def stream(self): return self.docs


class _Db:
    def __init__(self, docs): self.docs = docs
    def collection(self, name):
        assert name == 'email_action_suggestions'
        return _Suggestions(self.docs)


class _Gmail:
    def users(self): return self
    def getProfile(self, **kwargs): return _Req({'emailAddress': 'andre@ufjf.br'})
    def messages(self): return self
    def threads(self): return self
    def get(self, **kwargs):
        if kwargs['id'] == 'message-1':
            return _Req({'threadId': 'thread-1'})
        return _Req({'messages': [
            {'internalDate': '1', 'payload': {'headers': [{'name': 'From', 'value': 'proad@ufjf.br'}]}},
            {'internalDate': '2', 'payload': {'headers': [{'name': 'From', 'value': 'André <andre@ufjf.br>'}]}},
        ]})


class EmailDirectionTest(unittest.TestCase):
    def test_ultima_mensagem_do_usuario_fecha_pendencia(self):
        doc = _Doc('suggestion-1', {'google_message_id': 'message-1'})
        atualizar_direcao_emails_aplicados(_Db([doc]), _Gmail())
        self.assertTrue(doc.reference.data['ultima_mensagem_de_andre'])
        self.assertEqual(doc.reference.data['gmail_thread_id'], 'thread-1')
        self.assertEqual(doc.reference.data['internal_date'], '2')


if __name__ == '__main__':
    unittest.main()
