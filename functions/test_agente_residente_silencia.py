"""Com o agente residente ligado, o bot antigo nao manda o que o agente ja trata."""

import unittest
from datetime import datetime, timezone
from unittest import mock

import ai_notification_planner
import email_action_linker
import resposta_esperada_avisos
import whatsapp_ingest

ATIVO = mock.patch("atencao.agente_residente_ativo", return_value=True)


class TestSilencio(unittest.TestCase):
    @ATIVO
    def test_sugestao_de_email_nao_vira_cartao(self, _):
        send = mock.Mock()
        self.assertFalse(email_action_linker._send_suggestion_telegram(mock.Mock(), "1", "m", {}, send))
        send.assert_not_called()

    @ATIVO
    def test_resposta_esperada_nao_avisa(self, _):
        with mock.patch("telegram_utils._send_telegram_message_with_keyboard") as send:
            resposta_esperada_avisos._avisar_no_telegram(mock.Mock(), "a", {"classe": "R", "autor": "X"}, "ok")
        send.assert_not_called()

    @ATIVO
    def test_midia_pendente_nao_avisa(self, _):
        with mock.patch("main._send_telegram_message_raw") as send:
            whatsapp_ingest._alert_pending_media_window(mock.Mock(), "1", "w", "Chat", [{}], [])
        send.assert_not_called()

    @ATIVO
    def test_notificacao_da_ia_vira_delegada(self, _):
        doc = mock.Mock()
        db = mock.Mock()
        db.collection.return_value.where.return_value.where.return_value.stream.return_value = [doc]
        with mock.patch("main._send_telegram_message_raw_with_keyboard") as send:
            ai_notification_planner.dispatch_pending_ai_notifications(db, datetime(2026, 10, 25, tzinfo=timezone.utc))
        send.assert_not_called()
        self.assertEqual(doc.reference.update.call_args[0][0]["status"], "delegado_agente")


if __name__ == "__main__":
    unittest.main()
