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

sys.path.insert(0, '.')

from test_atencao import MockDb

from email_action_linker import queue_and_maybe_send_suggestion


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


if __name__ == "__main__":
    unittest.main()
