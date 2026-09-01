import sys
import unittest
from unittest import mock
from datetime import datetime

sys.path.insert(0, '.')
from tools.pausar_conversa import _parse_resume, preview, pausar


class _Ref:
    def __init__(self, data=None):
        self.data = data or {}
        self.set_calls, self.update_calls = [], []
    def get(self): return _Snap('ref', self.data, self)
    def set(self, data, merge=False): self.set_calls.append((data, merge)); self.data.update(data)
    def update(self, data): self.update_calls.append(data); self.data.update(data)


class _Snap:
    def __init__(self, ident, data, ref=None):
        self.id, self._data, self.exists = ident, data, data is not None
        self.reference = ref or _Ref(data)
    def to_dict(self): return dict(self._data or {})
    def get(self): return self


class _Collection:
    def __init__(self, docs=None, refs=None): self.docs, self.refs = docs or [], refs or {}
    def stream(self): return list(self.docs)
    def document(self, ident): return self.refs.setdefault(ident, _Ref())


class _Db:
    def __init__(self):
        self.task_ref = _Ref({'titulo': 'Ação', 'status': 'em andamento', 'whatsapp_vinculos': [{'chat_id': '55@c.us'}], 'plano_acao': []})
        self.inbox_ref = _Ref({'trecho': 'Pode olhar o processo?'})
        self.cols = {
            'perfil_pessoas': _Collection([_Snap('p', {'nome': 'Gabriela', 'telefone': '+55 27 99999-0000', 'whatsapp_chat_id': '55@c.us'})]),
            'whatsapp_chats': _Collection(),
            'tarefas': _Collection([_Snap('a1', self.task_ref.data, self.task_ref)], {'a1': self.task_ref}),
            'inbox_pendentes': _Collection(refs={}),
        }
    def collection(self, name):
        col = self.cols.setdefault(name, _Collection())
        if name == 'inbox_pendentes':
            # qualquer id do índice aponta ao mesmo registro neste fake
            original = col.document
            def document(_): return self.inbox_ref
            col.document = document
        return col


class _Ctx:
    def __init__(self): self.db = _Db()


class PausarConversaTest(unittest.TestCase):
    def test_atalho_amanha_manha_pula_fim_de_semana(self):
        target, phrase = _parse_resume("amanha_manha", datetime(2026, 9, 4, 17))
        self.assertEqual(target.isoformat(), "2026-09-07T08:00:00-03:00")
        self.assertEqual(phrase, "amanhã de manhã")

    def test_atalho_hoje_tarde(self):
        target, phrase = _parse_resume("hoje_tarde", datetime(2026, 9, 1, 10))
        self.assertEqual(target.hour, 14)
        self.assertEqual(phrase, "hoje à tarde")

    def test_preview_nao_enfileira_e_devolve_texto_exato(self):
        ctx = _Ctx()
        result = preview(ctx, {'contato_ou_grupo': 'Gabriela', 'retomar_em': 'amanha_manha'}, now=datetime(2026, 9, 1, 10))
        self.assertEqual(result['status'], 'aguardando_confirmacao')
        self.assertIn('Gabriela, vi sua mensagem.', result['mensagem'])
        self.assertEqual(ctx.db.inbox_ref.set_calls, [])
        self.assertEqual(ctx.db.task_ref.update_calls, [])

    def test_confirmada_enfileira_pausa_e_atualiza_acao(self):
        ctx = _Ctx()
        with mock.patch('tools.schedule_whatsapp_message.schedule_whatsapp_message', return_value='Mensagem ENFILEIRADA job_id=x') as enqueue, \
             mock.patch('tools.pausar_conversa.firestore.ArrayUnion', side_effect=lambda values: values):
            result = pausar(ctx, {'contato_ou_grupo': 'Gabriela', 'retomar_em': '2026-09-02T08:00:00-03:00'})
        self.assertEqual(result['status'], 'enfileirada')
        enqueue.assert_called_once()
        self.assertEqual(ctx.db.inbox_ref.set_calls[-1][0]['pausada_ate'], '2026-09-02T08:00:00-03:00')
        update = ctx.db.task_ref.update_calls[-1]
        self.assertEqual(update['plano_acao'][0]['estado'], 'aguardando_terceiro')
        self.assertIn('Conversa pausada com Gabriela', str(update['acompanhamento']))


if __name__ == '__main__':
    unittest.main()
