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
    def __init__(self, thread_messages=None):
        self.thread_messages = thread_messages or [
            {'internalDate': '1', 'payload': {'headers': [{'name': 'From', 'value': 'proad@ufjf.br'}]}},
            {'internalDate': '2', 'payload': {'headers': [{'name': 'From', 'value': 'André <andre@ufjf.br>'}]}},
        ]

    def users(self): return self
    def getProfile(self, **kwargs): return _Req({'emailAddress': 'andre@ufjf.br'})
    def messages(self): return self
    def threads(self): return self
    def get(self, **kwargs):
        if kwargs['id'] == 'message-1':
            return _Req({'threadId': 'thread-1'})
        return _Req({'messages': self.thread_messages})


class EmailDirectionTest(unittest.TestCase):
    def test_ultima_mensagem_do_usuario_fecha_pendencia(self):
        doc = _Doc('suggestion-1', {'google_message_id': 'message-1'})
        atualizar_direcao_emails_aplicados(_Db([doc]), _Gmail())
        self.assertTrue(doc.reference.data['ultima_mensagem_de_andre'])
        self.assertEqual(doc.reference.data['gmail_thread_id'], 'thread-1')
        self.assertEqual(doc.reference.data['internal_date'], '2')


class EmailDirectionSenderRefreshTest(unittest.TestCase):
    """DEV-2026-0004 sub-entrega 1/9 (causa-raiz do achado B1): `sender` deixa
    de ficar congelado no remetente original -- passa a refletir quem mandou a
    última mensagem da thread a cada refresh. Reproduz o caso relatado
    (Sabrina Panceri / Mayana-IFTO / FAPES): uma devolução (mailer-daemon)
    chegando como resposta à mensagem do André."""

    def test_devolucao_mailer_daemon_atualiza_sender_para_o_remetente_real(self):
        doc = _Doc('suggestion-sabrina', {
            'google_message_id': 'message-1',
            'sender': 'Sabrina Panceri <sabrina.panceri@example.com>',
            'origem_sinal': 'Sabrina Panceri <sabrina.panceri@example.com>',
        })
        gmail = _Gmail(thread_messages=[
            {'internalDate': '1', 'payload': {'headers': [
                {'name': 'From', 'value': 'Sabrina Panceri <sabrina.panceri@example.com>'}]}},
            {'internalDate': '2', 'payload': {'headers': [
                {'name': 'From', 'value': 'André <andre@ufjf.br>'}]}},
            {'internalDate': '3', 'payload': {'headers': [
                {'name': 'From', 'value': 'Mail Delivery Subsystem <mailer-daemon@googlemail.com>'}]}},
        ])
        atualizar_direcao_emails_aplicados(_Db([doc]), gmail)
        # a thread não fecha sozinha (mailer-daemon != andre@ufjf.br) -- isso é
        # tratado pelas sub-entregas seguintes (exclusão/realocação do item) --
        # mas o remetente gravado agora é o real, não mais o congelado.
        self.assertFalse(doc.reference.data['ultima_mensagem_de_andre'])
        self.assertEqual(
            doc.reference.data['sender'],
            'Mail Delivery Subsystem <mailer-daemon@googlemail.com>',
        )
        # origem_sinal (registro histórico de quem abriu o vínculo) não é tocado.
        self.assertEqual(
            doc.reference.data['origem_sinal'],
            'Sabrina Panceri <sabrina.panceri@example.com>',
        )

    def test_sender_atualizado_e_reconhecido_como_ruido_automatico(self):
        """Ponta a ponta com inbox_pendentes._noise_reason, usando o `sender` E
        o `snippet` como o refresh de verdade os deixa (não texto digitado à
        mão no teste): uma vez que `sender` reflete o remetente real da
        devolução, o filtro de ruído -- que já reconhecia `mailer-daemon` --
        passa a excluir o item corretamente (antes desta correção, `sender`
        continuaria "Mayana <mayana@ifto.edu.br>" e este reason daria None, ou
        seja, falsa "resposta pendente")."""
        from inbox_pendentes import _DEFAULT_DOMAINS, _DEFAULT_ENDINGS, _noise_reason

        doc = _Doc('suggestion-mayana', {
            'google_message_id': 'message-1',
            'sender': 'Mayana <mayana@ifto.edu.br>',
            'snippet': 'Mayana: segue o cronograma da visita técnica.',
        })
        gmail = _Gmail(thread_messages=[
            {'internalDate': '1', 'payload': {'headers': [{'name': 'From', 'value': 'Mayana <mayana@ifto.edu.br>'}]}},
            {'internalDate': '2', 'payload': {'headers': [{'name': 'From', 'value': 'André <andre@ufjf.br>'}]}},
            {'internalDate': '3', 'snippet': 'Delivery Status Notification (Failure)', 'payload': {'headers': [
                {'name': 'From', 'value': 'mailer-daemon@googlemail.com'}]}},
        ])
        atualizar_direcao_emails_aplicados(_Db([doc]), gmail)
        updated = doc.reference.data

        reason = _noise_reason(
            trecho=updated['snippet'],
            sender=updated['sender'],
            is_email=True,
            has_contact=False,
            has_task=True,
            domains=_DEFAULT_DOMAINS,
            endings=_DEFAULT_ENDINGS,
        )
        self.assertEqual(reason, 'automaticos')

    def test_troca_de_remetente_na_thread_atualiza_snippet_junto_com_sender(self):
        """Achado da revisão adversarial desta sub-entrega: atualizar `sender`
        sem atualizar `snippet` deixaria o contato certo ao lado de um trecho
        de uma mensagem antiga e diferente, sempre que outra pessoa (não uma
        devolução) assume a thread -- ex.: um assistente responde no lugar do
        contato original. Prova que os dois campos avançam juntos."""
        doc = _Doc('suggestion-troca', {
            'google_message_id': 'message-1',
            'sender': 'Gabriela <gabriela@ifes.edu.br>',
            'snippet': 'Gabriela: poderia revisar o anexo até sexta?',
        })
        gmail = _Gmail(thread_messages=[
            {'internalDate': '1', 'payload': {'headers': [{'name': 'From', 'value': 'Gabriela <gabriela@ifes.edu.br>'}]}},
            {'internalDate': '2', 'payload': {'headers': [{'name': 'From', 'value': 'André <andre@ufjf.br>'}]}},
            {'internalDate': '3', 'snippet': 'Marcos: assumindo esse assunto no lugar da Gabriela, segue o despacho.',
             'payload': {'headers': [{'name': 'From', 'value': 'Marcos Marinho <marcos@tjes.jus.br>'}]}},
        ])
        atualizar_direcao_emails_aplicados(_Db([doc]), gmail)
        updated = doc.reference.data
        self.assertEqual(updated['sender'], 'Marcos Marinho <marcos@tjes.jus.br>')
        self.assertEqual(updated['snippet'], 'Marcos: assumindo esse assunto no lugar da Gabriela, segue o despacho.')

    def test_ausencia_de_snippet_na_resposta_da_api_preserva_o_valor_anterior(self):
        """Mesma postura defensiva já usada para `sender`: se a resposta da API
        não trouxer `snippet` para a mensagem mais recente, o valor antigo
        sobrevive em vez de ser apagado."""
        doc = _Doc('suggestion-sem-snippet', {
            'google_message_id': 'message-1',
            'sender': 'Gabriela <gabriela@ifes.edu.br>',
            'snippet': 'Gabriela: poderia revisar o anexo até sexta?',
        })
        gmail = _Gmail(thread_messages=[
            {'internalDate': '1', 'payload': {'headers': [{'name': 'From', 'value': 'Gabriela <gabriela@ifes.edu.br>'}]}},
            {'internalDate': '2', 'payload': {'headers': [{'name': 'From', 'value': 'Gabriela <gabriela@ifes.edu.br>'}]}},
        ])
        atualizar_direcao_emails_aplicados(_Db([doc]), gmail)
        self.assertEqual(
            doc.reference.data['snippet'],
            'Gabriela: poderia revisar o anexo até sexta?',
        )


class EmailDirectionAndreEmToRefreshTest(unittest.TestCase):
    """DEV-2026-0004 sub-entrega 3/9: `andre_em_to` (André está no To da
    última mensagem da thread, não só em Cc) é recalculado a cada refresh --
    mesma disciplina de sender/snippet na sub-entrega 1/9, para não deixar o
    sinal congelado na mensagem que criou a sugestão."""

    def test_ultima_mensagem_so_com_andre_em_cc_corrige_para_false(self):
        doc = _Doc('suggestion-cc', {
            'google_message_id': 'message-1',
            'sender': 'Diretoria de Ensino <dae.rei@ifes.edu.br>',
            'andre_em_to': True,  # valor antigo, tem que ser corrigido no refresh
        })
        gmail = _Gmail(thread_messages=[
            {'internalDate': '1', 'payload': {'headers': [
                {'name': 'From', 'value': 'Diretoria de Ensino <dae.rei@ifes.edu.br>'},
                {'name': 'To', 'value': 'dae.rei@ifes.edu.br'},
                {'name': 'Cc', 'value': 'André <andre@ufjf.br>'},
            ]}},
        ])
        atualizar_direcao_emails_aplicados(_Db([doc]), gmail)
        self.assertFalse(doc.reference.data['andre_em_to'])

    def test_ultima_mensagem_com_andre_no_to_marca_true(self):
        doc = _Doc('suggestion-to', {'google_message_id': 'message-1', 'sender': 'Gabriela <gabriela@ifes.edu.br>'})
        gmail = _Gmail(thread_messages=[
            {'internalDate': '1', 'payload': {'headers': [
                {'name': 'From', 'value': 'Gabriela <gabriela@ifes.edu.br>'},
                {'name': 'To', 'value': 'andre@ufjf.br'},
            ]}},
        ])
        atualizar_direcao_emails_aplicados(_Db([doc]), gmail)
        self.assertTrue(doc.reference.data['andre_em_to'])

    def test_header_to_ausente_marca_none_nao_false(self):
        """Um Bcc puro (sem header To nenhum) não é o mesmo sinal que 'André
        só em Cc' -- fica None (não filtra) em vez de False (filtraria como
        informativo e esconderia um e-mail que pode ter ido só para ele)."""
        doc = _Doc('suggestion-sem-to', {'google_message_id': 'message-1', 'sender': 'Gabriela <gabriela@ifes.edu.br>'})
        gmail = _Gmail(thread_messages=[
            {'internalDate': '1', 'payload': {'headers': [{'name': 'From', 'value': 'Gabriela <gabriela@ifes.edu.br>'}]}},
        ])
        atualizar_direcao_emails_aplicados(_Db([doc]), gmail)
        self.assertIsNone(doc.reference.data['andre_em_to'])


if __name__ == '__main__':
    unittest.main()
