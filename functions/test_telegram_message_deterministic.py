"""Marcador de edição de rascunho (botão "✏️ Editar") em try_deterministic_reply.

Regressão de 25/09/2026: o dono pediu no Telegram "Cancele o envio de WhatsApp
... job_id ..." e recebeu "Não consegui atualizar o rascunho: Rascunho já
decidido (status atual: descartado)". A sessão ainda guardava o marcador de um
"✏️ Editar" antigo, o rascunho já tinha sido descartado, e o pedido foi
consumido como texto novo do rascunho em vez de chegar ao agente.
"""
import unittest
from unittest import mock

import telegram_message_deterministic as tmd


class TestMarcadorEdicaoRascunho(unittest.TestCase):
    def setUp(self):
        # Isola o ramo do outbox: nenhum outro atalho determinístico dispara.
        patches = {
            "_try_register_walk_block": None,
            "_extract_action_search_context_query": None,
            "_extract_natural_context_query": None,
            "_is_list_actions_request": (False, None),
            "_extract_action_lookup_query": None,
            "_is_reset_request": False,
        }
        for nome, retorno in patches.items():
            p = mock.patch.object(tmd, nome, return_value=retorno)
            p.start()
            self.addCleanup(p.stop)
        self.save = mock.patch.object(tmd, "_save_session").start()
        self.send = mock.patch.object(tmd, "_send_telegram_session_message").start()
        self.addCleanup(mock.patch.stopall)
        self.persist = mock.Mock()
        self.session = {"pending_outbox_edit": "rascunho-antigo"}

    def _responder(self, texto):
        return tmd.try_deterministic_reply(
            mock.Mock(), "tok", "123", texto, self.session, "gk", "texto",
            "masculina", {}, self.persist,
        )

    def _com_edicao(self, resultado):
        return mock.patch("outbox_aprovacao.aplicar_edicao_rascunho", return_value=resultado)

    def test_rascunho_ja_decidido_deixa_a_mensagem_seguir_para_o_agente(self):
        with self._com_edicao({"status": "already_decided",
                               "erro": "Rascunho já decidido (status atual: descartado)"}):
            tratada = self._responder("Cancele o envio de WhatsApp job_id abc. Não enviar.")

        self.assertFalse(tratada)
        self.send.assert_not_called()
        self.persist.assert_not_called()
        self.assertNotIn("pending_outbox_edit", self.session)

    def test_rascunho_inexistente_deixa_a_mensagem_seguir_para_o_agente(self):
        with self._com_edicao({"status": "not_found", "erro": "Rascunho 'x' não encontrado."}):
            tratada = self._responder("qual a minha agenda de amanhã?")

        self.assertFalse(tratada)
        self.send.assert_not_called()
        self.assertNotIn("pending_outbox_edit", self.session)

    def test_rascunho_editavel_continua_recebendo_o_texto_novo(self):
        with self._com_edicao({"status": "ok"}) as editar:
            tratada = self._responder("Texto novo do rascunho")

        self.assertTrue(tratada)
        editar.assert_called_once()
        self.assertEqual(editar.call_args.args[1:3], ("rascunho-antigo", "Texto novo do rascunho"))
        self.assertIn("atualizado com sucesso", self.send.call_args.args[3])

    def test_outro_erro_continua_avisando_o_dono(self):
        with self._com_edicao({"status": "erro_transacao", "erro": "falhou"}):
            tratada = self._responder("Texto novo do rascunho")

        self.assertTrue(tratada)
        self.assertIn("Não consegui atualizar o rascunho: falhou", self.send.call_args.args[3])


if __name__ == "__main__":
    unittest.main()
