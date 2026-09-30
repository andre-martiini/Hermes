"""Testes de `queue_and_maybe_send_suggestion` (functions/email_action_linker.py),
em particular o gap de idempotência no reenvio de Telegram após falha parcial:
se o doc de sugestão já existe (uma tentativa anterior gravou a sugestão) mas
`telegram_sent` ainda é False, uma nova chamada deve tentar reenviar só o
cartão, em vez de considerar o trabalho já concluído.

Reaproveita `MockDb`/`MockDoc`/`MockQuery` de test_atencao.py (mesmo padrão
usado pelos demais detectores/produtores de sugestão).
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, '.')

from test_atencao import MockDb

from email_action_linker import queue_and_maybe_send_suggestion, link_calendar_events_to_actions


TASK = {"id": "task-1", "titulo": "Processo X", "status": "em_andamento", "is_standby": False}


class TestQueueAndMaybeSendSuggestion(unittest.TestCase):
    def test_doc_novo_grava_e_envia(self):
        db = MockDb({"email_action_suggestions": {}})
        sent = []

        def send_fn(_db, chat_id, text, keyboard):
            sent.append((chat_id, text, keyboard))
            return True

        result = queue_and_maybe_send_suggestion(
            db,
            "sipac_123",
            canal="sipac",
            task=TASK,
            titulo_sinal="Processo 123",
            chat_id="chat-1",
            send_fn=send_fn,
        )

        self.assertTrue(result["telegram_sent"])
        self.assertEqual(len(sent), 1)
        doc = db.collection("email_action_suggestions").document("sipac_123")
        self.assertTrue(doc.to_dict()["telegram_sent"])

    def test_doc_ja_concluido_nao_reenvia(self):
        db = MockDb({
            "email_action_suggestions": {
                "sipac_123": {
                    "canal": "sipac",
                    "task_id": "task-1",
                    "status": "pending",
                    "telegram_sent": True,
                }
            }
        })
        sent = []

        def send_fn(_db, chat_id, text, keyboard):
            sent.append((chat_id, text, keyboard))
            return True

        result = queue_and_maybe_send_suggestion(
            db,
            "sipac_123",
            canal="sipac",
            task=TASK,
            titulo_sinal="Processo 123",
            chat_id="chat-1",
            send_fn=send_fn,
        )

        self.assertTrue(result["telegram_sent"])
        self.assertEqual(sent, [], "não deve reenviar quando telegram_sent já é True")

    def test_doc_existe_mas_envio_falhou_antes_retenta_so_o_envio(self):
        """
        Achado do gap de idempotência (registrado no diário de execução, P05
        sub-entrega 7/N): antes desta correção, `doc_ref.get().exists` sozinho
        fazia a função devolver `{}` sem nunca tentar reenviar, mesmo quando
        `telegram_sent` continuava False -- uma tentativa anterior havia
        gravado a sugestão mas falhado (ou foi interrompida) antes de
        confirmar o envio do cartão.
        """
        db = MockDb({
            "email_action_suggestions": {
                "sipac_123": {
                    "canal": "sipac",
                    "task_id": "task-1",
                    "task_titulo": "Processo X",
                    "status": "pending",
                    "telegram_sent": False,
                }
            }
        })
        sent = []

        def send_fn(_db, chat_id, text, keyboard):
            sent.append((chat_id, text, keyboard))
            return True

        result = queue_and_maybe_send_suggestion(
            db,
            "sipac_123",
            canal="sipac",
            task=TASK,
            titulo_sinal="Processo 123",
            chat_id="chat-1",
            send_fn=send_fn,
        )

        self.assertTrue(result["telegram_sent"])
        self.assertEqual(len(sent), 1, "deve tentar reenviar quando telegram_sent ainda é False")
        doc = db.collection("email_action_suggestions").document("sipac_123")
        self.assertTrue(doc.to_dict()["telegram_sent"])
        self.assertIn("sent_at", doc.to_dict())
        # os campos originais do doc (gravados na tentativa anterior) não são reescritos
        self.assertEqual(doc.to_dict()["task_titulo"], "Processo X")

    def test_doc_existe_envio_falha_de_novo_continua_nao_enviado(self):
        db = MockDb({
            "email_action_suggestions": {
                "sipac_123": {
                    "canal": "sipac",
                    "task_id": "task-1",
                    "status": "pending",
                    "telegram_sent": False,
                }
            }
        })

        def send_fn(_db, chat_id, text, keyboard):
            return False

        result = queue_and_maybe_send_suggestion(
            db,
            "sipac_123",
            canal="sipac",
            task=TASK,
            titulo_sinal="Processo 123",
            chat_id="chat-1",
            send_fn=send_fn,
        )

        self.assertFalse(result.get("telegram_sent"))
        doc = db.collection("email_action_suggestions").document("sipac_123")
        self.assertFalse(doc.to_dict()["telegram_sent"])

    def test_doc_existe_sem_chat_id_nao_tenta_enviar(self):
        """Chamador sem chat_id (ex.: sem chat padrão resolvido) não deve
        disparar tentativa de envio, mesmo com telegram_sent=False."""
        db = MockDb({
            "email_action_suggestions": {
                "sipac_123": {
                    "canal": "sipac",
                    "task_id": "task-1",
                    "status": "pending",
                    "telegram_sent": False,
                }
            }
        })
        sent = []

        def send_fn(_db, chat_id, text, keyboard):
            sent.append((chat_id, text, keyboard))
            return True

        result = queue_and_maybe_send_suggestion(
            db,
            "sipac_123",
            canal="sipac",
            task=TASK,
            titulo_sinal="Processo 123",
            chat_id=None,
            send_fn=send_fn,
        )

        self.assertFalse(result.get("telegram_sent"))
        self.assertEqual(sent, [])


class TestLinkCalendarEventsResend(unittest.TestCase):
    """
    Achado real da revisão adversarial desta sub-entrega: `link_calendar_events_to_actions`
    tinha uma pré-checagem de existência (`if suggestions_col.document(suggestion_id).get().exists:
    continue`) ANTES de chamar `queue_and_maybe_send_suggestion` -- isso tornava o reenvio
    corrigido acima morto (inalcançável) para o produtor de Calendar: um doc com
    telegram_sent=False nunca chegava à função que sabe retentar, porque o `continue`
    pulava a chamada inteira. Removida a pré-checagem; a idempotência agora vive só em
    `queue_and_maybe_send_suggestion`, igual aos demais produtores (SIPAC, WhatsApp, Monitor
    de Páginas), que nunca tiveram essa pré-checagem.
    """

    def _build_db(self, suggestion_doc=None):
        now = datetime.now(timezone.utc)
        event_fim = (now - timedelta(minutes=30)).isoformat()
        data = {
            "system": {"settings": {"email_action_linker": {"enabled": True}}},
            "tarefas": {
                "task-1": {
                    "titulo": "Reunião X",
                    "status": "em andamento",
                    "google_calendar_id": "gcal-1",
                }
            },
            "google_calendar_events": {
                "evt-1": {
                    "google_id": "gcal-1",
                    "titulo": "Reunião X",
                    "data_fim": event_fim,
                }
            },
            "email_action_suggestions": {},
        }
        if suggestion_doc is not None:
            data["email_action_suggestions"]["calendar_gcal-1"] = suggestion_doc
        return MockDb(data)

    def test_doc_existente_com_telegram_sent_false_e_reenviado_nao_pulado(self):
        db = self._build_db(suggestion_doc={
            "canal": "calendar",
            "task_id": "task-1",
            "status": "pending",
            "telegram_sent": False,
        })
        sent = []

        def send_fn(_db, chat_id, text, keyboard):
            sent.append((chat_id, text, keyboard))
            return True

        with mock.patch("main._cached_doc_get", side_effect=lambda db, coll, docid: db.collection(coll).document(docid).get()), \
             mock.patch("main._resolve_default_telegram_chat_id", return_value="chat-1"), \
             mock.patch("main._send_telegram_message_raw_with_keyboard", side_effect=send_fn):
            link_calendar_events_to_actions(db, sync_ref=mock.MagicMock(), logs=[])

        self.assertEqual(len(sent), 1, "doc existente com telegram_sent=False deve ser reenviado, não pulado")
        doc = db.collection("email_action_suggestions").document("calendar_gcal-1")
        self.assertTrue(doc.to_dict()["telegram_sent"])

    def test_doc_existente_com_telegram_sent_true_nao_e_reenviado(self):
        db = self._build_db(suggestion_doc={
            "canal": "calendar",
            "task_id": "task-1",
            "status": "pending",
            "telegram_sent": True,
        })
        sent = []

        def send_fn(_db, chat_id, text, keyboard):
            sent.append((chat_id, text, keyboard))
            return True

        with mock.patch("main._cached_doc_get", side_effect=lambda db, coll, docid: db.collection(coll).document(docid).get()), \
             mock.patch("main._resolve_default_telegram_chat_id", return_value="chat-1"), \
             mock.patch("main._send_telegram_message_raw_with_keyboard", side_effect=send_fn):
            link_calendar_events_to_actions(db, sync_ref=mock.MagicMock(), logs=[])

        self.assertEqual(sent, [], "doc já com telegram_sent=True não deve ser reenviado")

    def test_doc_novo_continua_gravando_e_enviando(self):
        db = self._build_db(suggestion_doc=None)
        sent = []

        def send_fn(_db, chat_id, text, keyboard):
            sent.append((chat_id, text, keyboard))
            return True

        with mock.patch("main._cached_doc_get", side_effect=lambda db, coll, docid: db.collection(coll).document(docid).get()), \
             mock.patch("main._resolve_default_telegram_chat_id", return_value="chat-1"), \
             mock.patch("main._send_telegram_message_raw_with_keyboard", side_effect=send_fn):
            link_calendar_events_to_actions(db, sync_ref=mock.MagicMock(), logs=[])

        self.assertEqual(len(sent), 1)
        doc = db.collection("email_action_suggestions").document("calendar_gcal-1")
        self.assertTrue(doc.exists)
        self.assertTrue(doc.to_dict()["telegram_sent"])


if __name__ == "__main__":
    unittest.main()
