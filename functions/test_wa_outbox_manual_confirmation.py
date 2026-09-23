"""Callbacks `wa_cancel:` e `wa_confirm_sent:` do outbox de WhatsApp no Telegram.

Cobre dois bugs reais encontrados em 16/09/2026 ao investigar o job
bae25bc6-0729-4213-a24d-c37feea5d687 (entregue as 16:28, nunca marcado "sent"):

1. `wa_cancel:` chamava `datetime.datetime.now(datetime.timezone.utc)`, mas o
   modulo importa `datetime` como a CLASSE (`from datetime import datetime,
   timezone`) -- isso estourava AttributeError, engolido pelo `except`
   ao redor, entao o Firestore nunca era atualizado mesmo o usuario recebendo
   "cancelado" na tela.
2. Nao existia forma de fechar o ciclo do fallback de notificacao manual
   (`ai_notification_planner.py::dispatch_scheduled_whatsapp_messages`): o
   botao "Sim, Enviar no WhatsApp" e um link wa.me, e o toque final de enviar
   e invisivel para o Hermes -- o job ficava preso em "notified" para sempre.
   `wa_confirm_sent:` fecha esse ciclo.

Terceiro bug real, corrigido ao construir `cancelar_envio_whatsapp`
(22/09/2026): `wa_cancel:` fazia um `.update()` direto, sem transacao nem
revalidacao de status -- uma corrida contra `claimOutboxMessage` (o worker,
que tambem disputa o mesmo documento numa transacao) podia sobrescrever
silenciosamente um envio ja 'sending'/'sent' de volta para 'canceled'. Agora
delega para `outbox_aprovacao.cancelar_envio` (mesma funcao transacional que
a tool MCP usa) -- a garantia de exclusao mutua em si esta coberta em
`TestCancelamento`, em test_outbox_aprovacao.py.
"""
import unittest
from unittest.mock import MagicMock, patch

import outbox_aprovacao
import telegram_callbacks_confirmacoes as tcc


class _CallbackTestBase(unittest.TestCase):
    def _chamar(self, data, doc_id="job123"):
        db = MagicMock()
        doc_ref = MagicMock()
        db.collection.return_value.document.return_value = doc_ref
        with patch.object(tcc, "_answer_callback_query"), \
             patch.object(tcc, "_send_telegram_message"):
            tratado = tcc.handle(
                db, "fake-token", "q1", "chat1", f"{data}{doc_id}",
                message={"message_id": 1}, session={}, copilot_session_id="cs1",
                _persist_callback_turn=MagicMock(),
                _pending_web_card=MagicMock(), _clear_pending_web_card=MagicMock(),
            )
        return tratado, db, doc_ref


class TestWaCancel(_CallbackTestBase):
    def test_delega_para_cancelar_envio_transacional_sem_escrita_direta(self):
        with patch.object(
            outbox_aprovacao, "cancelar_envio", return_value={"status": "ok"}
        ) as mock_cancelar:
            tratado, db, doc_ref = self._chamar("wa_cancel:")

        self.assertTrue(tratado)
        mock_cancelar.assert_called_once_with(db, "job123", cancelado_via="telegram")
        # Sem escrita direta no doc_ref -- toda a escrita agora vive dentro
        # da transacao de cancelar_envio (mockada aqui, testada de verdade
        # em TestCancelamento).
        doc_ref.update.assert_not_called()

    def test_falha_no_cancelamento_nao_estoura_o_callback(self):
        """cancelar_envio pode devolver erro (ja enviado, ja cancelado, sem
        suporte a transacao...) -- o callback do Telegram so precisa nao
        quebrar; a mensagem ao dono continua "cancelado" hoje (nao muda o
        texto de sucesso por resultado, so a chamada por baixo)."""
        with patch.object(
            outbox_aprovacao, "cancelar_envio",
            return_value={"status": "nao_cancelavel", "erro": "já está 'sent'"},
        ):
            tratado, _db, _doc_ref = self._chamar("wa_cancel:")
        self.assertTrue(tratado)


class TestWaConfirmSent(_CallbackTestBase):
    def test_confirma_envio_manual_e_marca_sent(self):
        import datetime
        tratado, db, doc_ref = self._chamar("wa_confirm_sent:")
        self.assertTrue(tratado)
        doc_ref.update.assert_called_once()
        payload = doc_ref.update.call_args[0][0]
        self.assertEqual(payload["status"], "sent")
        self.assertEqual(payload["sent_via"], "telegram_confirmacao_manual")
        self.assertIsInstance(payload["sent_at"], datetime.datetime)


if __name__ == "__main__":
    unittest.main()
