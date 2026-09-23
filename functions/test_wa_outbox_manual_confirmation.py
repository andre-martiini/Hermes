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

Terceiro e quarto bugs reais, corrigidos ao construir `cancelar_envio_whatsapp`
(22/09/2026):

3. `wa_cancel:` fazia um `.update()` direto, sem transacao nem revalidacao de
   status -- uma corrida contra `claimOutboxMessage` (o worker, que tambem
   disputa o mesmo documento numa transacao) podia sobrescrever
   silenciosamente um envio ja 'sending'/'sent' de volta para 'canceled'. Agora
   delega para `outbox_aprovacao.cancelar_envio` (mesma funcao transacional que
   a tool MCP usa) -- a garantia de exclusao mutua em si esta coberta em
   `TestCancelamento`, em test_outbox_aprovacao.py.
4. Achado da revisao adversarial da propria correcao (3): `wa_cancel:`
   respondia "cancelado" ao dono incondicionalmente, mesmo quando
   `cancelar_envio` recusava (ja enviado, ja em outro estado...) -- o toque no
   botao parecia ter funcionado mesmo quando nao funcionou. Agora o resultado
   real de `cancelar_envio` decide o toast e o texto mandado ao dono.
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

    def _chamar_com_mocks(self, data, doc_id="job123"):
        """Como `_chamar`, mas devolve os mocks de `_answer_callback_query` e
        `_send_telegram_message` para inspecionar o texto real mandado ao
        dono -- necessário para testar que o resultado de `cancelar_envio`
        (ok/erro) decide a mensagem, não um texto fixo."""
        db = MagicMock()
        doc_ref = MagicMock()
        db.collection.return_value.document.return_value = doc_ref
        with patch.object(tcc, "_answer_callback_query") as mock_answer, \
             patch.object(tcc, "_send_telegram_message") as mock_send:
            tratado = tcc.handle(
                db, "fake-token", "q1", "chat1", f"{data}{doc_id}",
                message={"message_id": 1}, session={}, copilot_session_id="cs1",
                _persist_callback_turn=MagicMock(),
                _pending_web_card=MagicMock(), _clear_pending_web_card=MagicMock(),
            )
        return tratado, mock_answer, mock_send


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

    def test_sucesso_informa_cancelado(self):
        with patch.object(outbox_aprovacao, "cancelar_envio", return_value={"status": "ok"}):
            tratado, mock_answer, mock_send = self._chamar_com_mocks("wa_cancel:")
        self.assertTrue(tratado)
        mock_answer.assert_called_once_with("fake-token", "q1", "Agendamento cancelado.")
        texto = mock_send.call_args[0][2]
        self.assertIn("foi cancelado", texto)

    def test_ja_cancelado_idempotente_tambem_informa_cancelado(self):
        with patch.object(
            outbox_aprovacao, "cancelar_envio", return_value={"status": "already_canceled"}
        ):
            tratado, _mock_answer, mock_send = self._chamar_com_mocks("wa_cancel:")
        self.assertTrue(tratado)
        self.assertIn("foi cancelado", mock_send.call_args[0][2])

    def test_falha_no_cancelamento_informa_status_real_ao_dono(self):
        """Achado da revisão adversarial (22/09/2026): antes desta correção,
        o dono via "cancelado" mesmo quando cancelar_envio recusava (já
        enviado, por exemplo) — o toque no botão parecia ter funcionado sem
        ter funcionado. Agora o texto (e o toast) refletem o resultado real,
        em vez de um texto de sucesso fixo."""
        with patch.object(
            outbox_aprovacao, "cancelar_envio",
            return_value={
                "status": "nao_cancelavel",
                "erro": "não é possível cancelar: já está 'sent'",
                "status_atual": "sent",
            },
        ):
            tratado, mock_answer, mock_send = self._chamar_com_mocks("wa_cancel:")
        self.assertTrue(tratado)
        toast = mock_answer.call_args[0][2]
        self.assertIn("Não foi possível cancelar", toast)
        texto = mock_send.call_args[0][2]
        self.assertIn("sent", texto)
        self.assertNotIn("foi cancelado", texto)

    def test_nao_encontrado_informa_ao_dono(self):
        with patch.object(outbox_aprovacao, "cancelar_envio", return_value={"status": "not_found"}):
            tratado, _mock_answer, mock_send = self._chamar_com_mocks("wa_cancel:")
        self.assertTrue(tratado)
        self.assertIn("não encontrado", mock_send.call_args[0][2])

    def test_erro_de_transacao_nao_estoura_e_informa_falha(self):
        with patch.object(
            outbox_aprovacao, "cancelar_envio",
            return_value={"status": "erro_transacao", "erro": "boom"},
        ):
            tratado, _mock_answer, mock_send = self._chamar_com_mocks("wa_cancel:")
        self.assertTrue(tratado)
        self.assertIn("Falha ao tentar cancelar", mock_send.call_args[0][2])

    def test_excecao_do_cancelar_envio_nao_estoura_e_informa_falha(self):
        with patch.object(outbox_aprovacao, "cancelar_envio", side_effect=RuntimeError("boom")):
            tratado, _mock_answer, mock_send = self._chamar_com_mocks("wa_cancel:")
        self.assertTrue(tratado)
        self.assertIn("Falha ao tentar cancelar", mock_send.call_args[0][2])


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
