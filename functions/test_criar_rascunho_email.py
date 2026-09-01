import base64
import sys
import types
import unittest
from email import policy
from email.parser import BytesParser
from unittest import mock

sys.path.insert(0, '.')
from tools import anexar_arquivo as aa
from tools.criar_rascunho_email import _thread_recipients, criar


class _Req:
    def __init__(self, value): self.value = value
    def execute(self): return self.value


class _Gmail:
    def __init__(self): self.created = None
    def users(self): return self
    def drafts(self): return self
    def create(self, **kwargs): self.created = kwargs['body']; return _Req({'id': 'draft-1'})
    def threads(self): return self
    def get(self, **kwargs):
        return _Req({'messages': [{'payload': {'headers': [
            {'name': 'From', 'value': 'proad@ufjf.br'}, {'name': 'Message-ID', 'value': '<m1>'},
        ]}}]})


class _Ctx: pass


class CriarRascunhoEmailTest(unittest.TestCase):
    def test_rejeita_base64_sem_chamar_gmail(self):
        result = criar(_Ctx(), {'para': ['a@b'], 'assunto': 'x', 'corpo': 'y', 'conteudo_base64': 'AA=='})
        self.assertIn('preparar_upload', result['erro'])

    def test_herda_destinatario_da_thread(self):
        recipients, headers = _thread_recipients(_Gmail(), 'thread-1')
        self.assertEqual(recipients, ['proad@ufjf.br'])
        self.assertEqual(headers['message-id'], '<m1>')

    def test_fixture_por_referencia_vira_mime_com_sha_igual(self):
        fixture = b'%PDF-1.4\n' + b'x' * (100 * 1024)
        gmail = _Gmail()
        module = types.SimpleNamespace(get_gmail_service=lambda: gmail)
        with mock.patch.dict(sys.modules, {'main': module}), \
             mock.patch('tools.anexar_arquivo.resolver_anexo_por_referencia', return_value=(fixture, 'prova.pdf')):
            result = criar(_Ctx(), {'para': ['destino@ufjf.br'], 'assunto': 'Prova', 'corpo': '**segue**',
                                    'anexos': [{'drive_file_id': 'arquivo-drive'}]})
        raw = base64.urlsafe_b64decode(gmail.created['message']['raw'])
        attached = list(BytesParser(policy=policy.default).parsebytes(raw).iter_attachments())
        self.assertEqual(len(attached), 1)
        self.assertEqual(result['anexos'][0]['sha256'], __import__('hashlib').sha256(attached[0].get_payload(decode=True)).hexdigest())


class GmailAttachmentReferenceTest(unittest.TestCase):
    def test_attachment_id_exato_e_nome_divergente_falha(self):
        service = _AttachmentService()
        with mock.patch.dict(sys.modules, {'main': types.SimpleNamespace(get_gmail_service=lambda: service)}):
            with self.assertRaisesRegex(ValueError, 'diferentes'):
                aa._do_gmail({'gmail_message_id': 'm', 'attachment_id': 'id-pdf', 'nome_anexo': 'planilha'})

    def test_mensagem_com_um_anexo_aceita_so_message_id(self):
        service = _AttachmentService()
        with mock.patch.dict(sys.modules, {'main': types.SimpleNamespace(get_gmail_service=lambda: service)}):
            data, name = aa._do_gmail({'gmail_message_id': 'm'})
        self.assertEqual((data, name), (b'pdf', 'prova.pdf'))


class _AttachmentService:
    def users(self): return self
    def messages(self): return self
    def attachments(self): return self
    def get(self, **kwargs):
        if 'format' in kwargs:
            return _Req({'payload': {'parts': [{'filename': 'prova.pdf', 'body': {'attachmentId': 'id-pdf'}}]}})
        return _Req({'data': base64.urlsafe_b64encode(b'pdf').decode()})


if __name__ == '__main__':
    unittest.main()
