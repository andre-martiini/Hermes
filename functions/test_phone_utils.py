"""A regra canonica de casamento contato ↔ WhatsApp.

O que estes testes travam e a migracao do WhatsApp para `@lid`.

Ate 2026 o `chat_id` carregava o telefone (`5527999999999@c.us`) e extrair os
ultimos 8 digitos dali bastava. O WhatsApp passou a identificar contato
individual por `@lid`, que **nao deriva do numero**. Na varredura de
27/08/2026: 450 chats `@lid`, 247 grupos e 2 `@c.us` — um deles a conta do
sistema. O vinculo automatico rendia zero, e rendia zero em silencio, porque
"nenhuma correspondencia" e resposta valida de um matcher.

O perigo aqui nao e nao casar: e casar errado. `@lid` e uma sequencia de
digitos; se ela entrasse no matcher como se fosse telefone, dois numeros
poderiam colidir nos ultimos 8 digitos e vincular a pessoa errada a uma
conversa. Por isso `@lid` sem telefone resolvido devolve vazio, e nao um
palpite.

Uso: functions/venv/Scripts/python.exe -m unittest test_phone_utils
"""

import unittest

from phone_utils import chat_id_last8, last8, whatsapp_chat_last8


class TestLast8(unittest.TestCase):

    def test_extrai_os_ultimos_oito_digitos(self):
        self.assertEqual(last8("+55 27 99999-1234"), "99991234")

    def test_ignora_pontuacao(self):
        self.assertEqual(last8("(27) 3333-4444"), "33334444")

    def test_curto_demais_devolve_vazio(self):
        """Menos de 8 digitos casaria com gente demais."""
        self.assertEqual(last8("1234567"), "")

    def test_vazio_e_nulo(self):
        for valor in ("", None, "   ", "sem numero"):
            self.assertEqual(last8(valor), "")


class TestChatIdLegado(unittest.TestCase):

    def test_c_us_ainda_funciona(self):
        self.assertEqual(chat_id_last8("5527999991234@c.us"), "99991234")

    def test_grupo_devolve_vazio(self):
        self.assertEqual(chat_id_last8("120363043383762406@g.us"), "")

    def test_lid_devolve_vazio(self):
        """O ponto do arquivo: `@lid` não é telefone e não pode virar um."""
        self.assertEqual(chat_id_last8("10059333525578@lid"), "")


class TestWhatsappChatLast8(unittest.TestCase):

    def test_prefere_o_telefone_resolvido(self):
        self.assertEqual(
            whatsapp_chat_last8("10059333525578@lid", "5527999991234"), "99991234")

    def test_lid_sem_telefone_nao_chuta(self):
        """Sem número resolvido, vazio — nunca os dígitos do próprio @lid.

        Se o @lid entrasse como se fosse telefone, dois contatos poderiam
        colidir nos últimos 8 dígitos e o vínculo cairia na pessoa errada.
        """
        self.assertEqual(whatsapp_chat_last8("10059333525578@lid"), "")
        self.assertEqual(whatsapp_chat_last8("10059333525578@lid", ""), "")
        self.assertEqual(whatsapp_chat_last8("10059333525578@lid", None), "")

    def test_c_us_sem_contact_number_usa_o_id(self):
        """Chat antigo continua casando sem depender do worker ter resolvido."""
        self.assertEqual(whatsapp_chat_last8("5527999991234@c.us"), "99991234")

    def test_telefone_resolvido_vence_o_id(self):
        """Se os dois existem, o campo explícito manda — foi ele que veio da API."""
        self.assertEqual(
            whatsapp_chat_last8("5527000000000@c.us", "+55 27 99999-1234"), "99991234")

    def test_grupo_nunca_casa(self):
        self.assertEqual(whatsapp_chat_last8("120363043383762406@g.us"), "")

    def test_telefone_invalido_cai_no_id(self):
        """Número curto demais não vale; o @c.us ainda serve de caminho."""
        self.assertEqual(whatsapp_chat_last8("5527999991234@c.us", "123"), "99991234")


if __name__ == "__main__":
    unittest.main()
