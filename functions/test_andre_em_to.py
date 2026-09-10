import sys
import unittest

sys.path.insert(0, '.')

from email_action_linker import _andre_em_to, _header_value


class HeaderValueTest(unittest.TestCase):
    def test_le_header_case_insensitive(self):
        msg = {'payload': {'headers': [{'name': 'To', 'value': 'andre@ufjf.br'}]}}
        self.assertEqual(_header_value(msg, 'to'), 'andre@ufjf.br')
        self.assertEqual(_header_value(msg, 'TO'), 'andre@ufjf.br')

    def test_header_ausente_devolve_string_vazia(self):
        msg = {'payload': {'headers': [{'name': 'From', 'value': 'x@example.com'}]}}
        self.assertEqual(_header_value(msg, 'To'), '')

    def test_payload_ausente_nao_estoura(self):
        self.assertEqual(_header_value({}, 'To'), '')


class AndreEmToTest(unittest.TestCase):
    """DEV-2026-0004 sub-entrega 3/9 -- sinal usado por
    `inbox_pendentes._noise_reason` para classificar como 'informativo' um
    e-mail onde André só está em Cc (achado B, caso 2 da demanda: Diretoria
    de Ensino BSF, e-mail endereçado a dae.rei@ifes.edu.br com André em
    cópia -- ele nem era destinatário direto)."""

    def test_andre_no_to_unico_destinatario(self):
        msg = {'payload': {'headers': [{'name': 'To', 'value': 'André <andre@ufjf.br>'}]}}
        self.assertTrue(_andre_em_to(msg, 'andre@ufjf.br'))

    def test_andre_no_to_entre_varios_destinatarios(self):
        msg = {'payload': {'headers': [
            {'name': 'To', 'value': 'dae.rei@ifes.edu.br, André <andre@ufjf.br>, outra@ifes.edu.br'},
        ]}}
        self.assertTrue(_andre_em_to(msg, 'andre@ufjf.br'))

    def test_andre_so_em_cc_devolve_false(self):
        msg = {'payload': {'headers': [
            {'name': 'To', 'value': 'dae.rei@ifes.edu.br'},
            {'name': 'Cc', 'value': 'André <andre@ufjf.br>'},
        ]}}
        self.assertFalse(_andre_em_to(msg, 'andre@ufjf.br'))

    def test_andre_ausente_de_ambos_devolve_false(self):
        msg = {'payload': {'headers': [{'name': 'To', 'value': 'outra@ifes.edu.br'}]}}
        self.assertFalse(_andre_em_to(msg, 'andre@ufjf.br'))

    def test_comparacao_e_case_insensitive(self):
        msg = {'payload': {'headers': [{'name': 'To', 'value': 'ANDRE@UFJF.BR'}]}}
        self.assertTrue(_andre_em_to(msg, 'andre@ufjf.br'))

    def test_sem_own_email_devolve_none(self):
        """Sem `own_email` (ex.: falha ao consultar a conta via getProfile),
        não dá para saber com confiança -- o chamador (`_noise_reason`) só
        filtra em `False` explícito, nunca em dúvida (`None`)."""
        msg = {'payload': {'headers': [{'name': 'To', 'value': 'andre@ufjf.br'}]}}
        self.assertIsNone(_andre_em_to(msg, ''))

    def test_sem_header_to_devolve_none_nao_false(self):
        """Um Bcc puro (mensagem sem header To nenhum) não é o mesmo sinal
        que 'André só está em Cc' -- fica None (não filtra), não False."""
        msg = {'payload': {'headers': [{'name': 'From', 'value': 'gabriela@ifes.edu.br'}]}}
        self.assertIsNone(_andre_em_to(msg, 'andre@ufjf.br'))

    def test_header_to_vazio_devolve_none(self):
        msg = {'payload': {'headers': [{'name': 'To', 'value': '   '}]}}
        self.assertIsNone(_andre_em_to(msg, 'andre@ufjf.br'))


if __name__ == '__main__':
    unittest.main()
