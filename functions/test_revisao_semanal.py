"""Testes da revisão semanal com proposta de reagendamento em lote (functions/revisao_semanal.py)."""

from datetime import datetime, timezone
import json
import unittest
from unittest.mock import MagicMock, patch
import uuid

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from revisao_semanal import (
    COLLECTION_PROPOSTAS,
    eh_tarefa_atrasada,
    propor_reagendamento_semanal,
    _TZ_SP,
)


class MockDoc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = self

    def to_dict(self):
        return dict(self._data or {})

    def get(self):
        return self

    def update(self, fields):
        if self._data is not None:
            self._data.update(fields)

    def set(self, fields, merge=False):
        if self._data is None:
            self._data = {}
        if merge:
            self._data.update(fields)
        else:
            self._data = dict(fields)
        self.exists = True


class MockQuery:
    def __init__(self, docs, filters=None, limit_val=None):
        self.docs = docs
        self.filters = filters or []
        self.limit_val = limit_val

    def where(self, field, op, val):
        new_filters = list(self.filters)
        new_filters.append((field, op, val))
        return MockQuery(self.docs, new_filters, self.limit_val)

    def limit(self, val):
        return MockQuery(self.docs, self.filters, limit_val=val)

    def stream(self):
        filtered = []
        for d in self.docs:
            data = d.to_dict()
            match = True
            for field, op, val in self.filters:
                if op == "==" and data.get(field) != val:
                    match = False
                    break
                elif op == "in" and data.get(field) not in val:
                    match = False
                    break
            if match:
                filtered.append(d)
        if self.limit_val is not None:
            filtered = filtered[:self.limit_val]
        return filtered

    def get(self):
        return self.stream()

    def document(self, wanted=None):
        if wanted is None:
            auto_id = f"prop-{uuid.uuid4().hex[:8]}"
            new_doc = MockDoc(auto_id, {})
            self.docs.append(new_doc)
            return new_doc
        return next((d for d in self.docs if d.id == wanted), MockDoc(wanted, None))


class MockDb:
    def __init__(self, data=None):
        self.data = data if data is not None else {}
        self._collections = {}

    def collection(self, name):
        if name not in self._collections:
            docs = [MockDoc(k, v) for k, v in self.data.get(name, {}).items()]
            self._collections[name] = MockQuery(docs)
        return self._collections[name]


class TestEhTarefaAtrasada(unittest.TestCase):
    def setUp(self):
        self.hoje = "2026-09-07"

    def test_em_andamento_com_data_limite_passada(self):
        tarefa = {"status": "em andamento", "data_limite": "2026-09-05"}
        self.assertTrue(eh_tarefa_atrasada(tarefa, self.hoje))

    def test_standby_com_data_limite_passada(self):
        tarefa = {"status": "stand-by", "data_limite": "2026-09-01"}
        self.assertTrue(eh_tarefa_atrasada(tarefa, self.hoje))

    def test_sem_data_limite_com_prazo_final_passado(self):
        tarefa = {"status": "em andamento", "data_limite": None, "prazo_final": "2026-09-04"}
        self.assertTrue(eh_tarefa_atrasada(tarefa, self.hoje))

    def test_com_data_limite_hoje(self):
        tarefa = {"status": "em andamento", "data_limite": "2026-09-07"}
        self.assertFalse(eh_tarefa_atrasada(tarefa, self.hoje))

    def test_com_data_limite_futura(self):
        tarefa = {"status": "em andamento", "data_limite": "2026-09-10"}
        self.assertFalse(eh_tarefa_atrasada(tarefa, self.hoje))

    def test_concluida_ou_cancelada_ignorado(self):
        self.assertFalse(eh_tarefa_atrasada({"status": "concluído", "data_limite": "2026-09-01"}, self.hoje))
        self.assertFalse(eh_tarefa_atrasada({"status": "cancelado", "data_limite": "2026-09-01"}, self.hoje))

    def test_sem_data_nenhuma(self):
        self.assertFalse(eh_tarefa_atrasada({"status": "em andamento"}, self.hoje))
        self.assertFalse(eh_tarefa_atrasada({"status": "em andamento", "data_limite": ""}, self.hoje))

    def test_input_invalido(self):
        self.assertFalse(eh_tarefa_atrasada({}, self.hoje))
        self.assertFalse(eh_tarefa_atrasada(None, self.hoje))


class TestProporReagendamentoSemanal(unittest.TestCase):
    def setUp(self):
        self.tz_sp = zoneinfo.ZoneInfo("America/Sao_Paulo")
        self.segunda = datetime(2026, 9, 7, 5, 15, tzinfo=self.tz_sp)

    def test_sem_candidatas_silencio_e_padrao(self):
        db = MockDb({
            "tarefas": {
                "t1": {"status": "em andamento", "data_limite": "2026-09-08"},  # futura
                "t2": {"status": "concluído", "data_limite": "2026-09-01"},   # concluída
            },
            COLLECTION_PROPOSTAS: {},
        })

        res = propor_reagendamento_semanal(db, now=self.segunda)
        self.assertEqual(res["status"], "nenhuma_candidata")
        self.assertEqual(res["candidatas"], 0)
        # Nenhuma proposta foi gravada
        self.assertEqual(len(db.collection(COLLECTION_PROPOSTAS).stream()), 0)

    def test_proposta_pending_ja_existente_trava_duplicata(self):
        db = MockDb({
            "tarefas": {
                "t1": {"status": "em andamento", "data_limite": "2026-09-01"},
            },
            COLLECTION_PROPOSTAS: {
                "prop-1": {
                    "status": "pending",
                    "items": [{"task_id": "t1"}],
                }
            },
        })

        res = propor_reagendamento_semanal(db, now=self.segunda)
        self.assertEqual(res["status"], "pulado_ja_existe_pendente")
        self.assertEqual(res["proposta_id"], "prop-1")
        # Mantém apenas a proposta original
        self.assertEqual(len(db.collection(COLLECTION_PROPOSTAS).stream()), 1)

    @patch("main._resolve_default_telegram_chat_id", return_value="123456")
    @patch("main._send_telegram_message_raw_with_keyboard", return_value=True)
    def test_com_candidatas_cria_proposta_e_envia_telegram(self, mock_send, mock_chat_id):
        db = MockDb({
            "tarefas": {
                "t1": {"titulo": "Renovar alvará", "status": "em andamento", "data_limite": "2026-09-01", "data_criacao": "2026-08-01"},
                "t2": {"titulo": "Comprar insumos", "status": "stand-by", "data_limite": "2026-09-02", "data_criacao": "2026-08-02"},
                "t3": {"titulo": "Ação em dia", "status": "em andamento", "data_limite": "2026-09-10"},
            },
            COLLECTION_PROPOSTAS: {},
        })

        res = propor_reagendamento_semanal(db, now=self.segunda)

        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["total_acoes"], 2)
        self.assertTrue(res["telegram_sent"])

        # Verifica doc gravado em reagendamentos_propostos
        propostas = list(db.collection(COLLECTION_PROPOSTAS).stream())
        self.assertEqual(len(propostas), 1)
        prop_data = propostas[0].to_dict()
        self.assertEqual(prop_data["status"], "pending")
        self.assertEqual(len(prop_data["items"]), 2)
        self.assertIn("t1", [it["task_id"] for it in prop_data["items"]])
        self.assertIn("t2", [it["task_id"] for it in prop_data["items"]])

        # Verifica chamada ao Telegram
        mock_send.assert_called_once()
        args, _ = mock_send.call_args
        _, chat_id, text, keyboard = args
        self.assertEqual(chat_id, "123456")
        self.assertIn("2 ação(ões)", text)
        self.assertIn("Renovar alvará", text)
        self.assertIn("Comprar insumos", text)

        # Teclado inline com os 2 botões pedidos no handoff
        self.assertEqual(len(keyboard), 1)
        self.assertEqual(len(keyboard[0]), 2)
        self.assertEqual(keyboard[0][0]["text"], "✅ Aplicar tudo")
        self.assertEqual(keyboard[0][0]["callback_data"], f"reagendamento_lote:{propostas[0].id}:aplicar")
        self.assertEqual(keyboard[0][1]["text"], "❌ Descartar")
        self.assertEqual(keyboard[0][1]["callback_data"], f"reagendamento_lote:{propostas[0].id}:descartar")


class TestCallbackReagendamentoLote(unittest.TestCase):
    def setUp(self):
        self.token = "fake-token"
        self.query_id = "qid-123"
        self.chat_id = "12345"

    @patch("hermes_core_logic._send_telegram_message")
    @patch("hermes_core_logic._answer_callback_query")
    @patch("hermes_core_logic._persist_copilot_message")
    @patch("hermes_core_logic._save_session")
    @patch("hermes_core_logic._ensure_copilot_session", return_value="copilot-sess-1")
    @patch("hermes_core_logic._get_session", return_value={})
    @patch("hermes_core_logic._get_allowed_chat_id", return_value=None)
    @patch("main.confirmarReagendamentoEmLote")
    def test_callback_aplicar_sucesso(
        self,
        mock_confirmar,
        mock_allowed,
        mock_get_sess,
        mock_ensure_sess,
        mock_save_sess,
        mock_persist_msg,
        mock_answer_cb,
        mock_send_msg,
    ):
        from hermes_core_logic import _handle_telegram_callback

        mock_confirmar.return_value = {"ok": True}

        db = MockDb({
            COLLECTION_PROPOSTAS: {
                "prop-1": {
                    "status": "pending",
                    "items": [
                        {"task_id": "t1", "nova_data_limite": "2026-09-08"},
                        {"task_id": "t2", "nova_data_limite": "2026-09-09"},
                    ],
                    "justificativa": "Revisão semanal",
                }
            }
        })

        cb_query = {
            "id": self.query_id,
            "data": "reagendamento_lote:prop-1:aplicar",
            "message": {"chat": {"id": self.chat_id}},
            "from": {"id": 12345, "first_name": "Andre"},
        }

        resp = _handle_telegram_callback(db, self.token, cb_query)
        self.assertEqual(resp.status_code, 200)

        # Verifica que invocou confirmarReagendamentoEmLote
        mock_confirmar.assert_called_once()
        call_req = mock_confirmar.call_args[0][0]
        self.assertEqual(len(call_req.data["items"]), 2)
        self.assertEqual(call_req.data["justificativa"], "Revisão semanal")

        # Verifica doc atualizado para 'aplicado'
        doc = db.collection(COLLECTION_PROPOSTAS).document("prop-1")
        self.assertEqual(doc.to_dict()["status"], "aplicado")
        self.assertIsNotNone(doc.to_dict().get("aplicado_em"))

        # Verifica toast e mensagem
        mock_answer_cb.assert_called_with(self.token, self.query_id, "2 ações reagendadas!")
        mock_send_msg.assert_called_once()
        self.assertIn("✅ Reagendamento em lote aplicado", mock_send_msg.call_args[0][2])

    @patch("hermes_core_logic._send_telegram_message")
    @patch("hermes_core_logic._answer_callback_query")
    @patch("hermes_core_logic._persist_copilot_message")
    @patch("hermes_core_logic._save_session")
    @patch("hermes_core_logic._ensure_copilot_session", return_value="copilot-sess-1")
    @patch("hermes_core_logic._get_session", return_value={})
    @patch("hermes_core_logic._get_allowed_chat_id", return_value=None)
    @patch("main.confirmarReagendamentoEmLote")
    def test_callback_aplicar_ja_processada_evita_duplo_clique(
        self,
        mock_confirmar,
        mock_allowed,
        mock_get_sess,
        mock_ensure_sess,
        mock_save_sess,
        mock_persist_msg,
        mock_answer_cb,
        mock_send_msg,
    ):
        from hermes_core_logic import _handle_telegram_callback

        db = MockDb({
            COLLECTION_PROPOSTAS: {
                "prop-1": {
                    "status": "aplicado",
                    "items": [{"task_id": "t1"}],
                }
            }
        })

        cb_query = {
            "id": self.query_id,
            "data": "reagendamento_lote:prop-1:aplicar",
            "message": {"chat": {"id": self.chat_id}},
            "from": {"id": 12345},
        }

        resp = _handle_telegram_callback(db, self.token, cb_query)
        self.assertEqual(resp.status_code, 200)

        # Não deve chamar confirmação novamente
        mock_confirmar.assert_not_called()
        mock_answer_cb.assert_called_with(self.token, self.query_id, "Proposta já processada (aplicado).")
        mock_send_msg.assert_not_called()

    @patch("hermes_core_logic._send_telegram_message")
    @patch("hermes_core_logic._answer_callback_query")
    @patch("hermes_core_logic._persist_copilot_message")
    @patch("hermes_core_logic._save_session")
    @patch("hermes_core_logic._ensure_copilot_session", return_value="copilot-sess-1")
    @patch("hermes_core_logic._get_session", return_value={})
    @patch("hermes_core_logic._get_allowed_chat_id", return_value=None)
    @patch("main.confirmarReagendamentoEmLote")
    def test_callback_descartar(
        self,
        mock_confirmar,
        mock_allowed,
        mock_get_sess,
        mock_ensure_sess,
        mock_save_sess,
        mock_persist_msg,
        mock_answer_cb,
        mock_send_msg,
    ):
        from hermes_core_logic import _handle_telegram_callback

        db = MockDb({
            COLLECTION_PROPOSTAS: {
                "prop-1": {
                    "status": "pending",
                    "items": [{"task_id": "t1"}],
                }
            }
        })

        cb_query = {
            "id": self.query_id,
            "data": "reagendamento_lote:prop-1:descartar",
            "message": {"chat": {"id": self.chat_id}},
            "from": {"id": 12345},
        }

        resp = _handle_telegram_callback(db, self.token, cb_query)
        self.assertEqual(resp.status_code, 200)

        # Não chama a callable de aplicar
        mock_confirmar.assert_not_called()

        # Doc atualizado para 'descartado'
        doc = db.collection(COLLECTION_PROPOSTAS).document("prop-1")
        self.assertEqual(doc.to_dict()["status"], "descartado")
        self.assertIsNotNone(doc.to_dict().get("descartado_em"))

        mock_answer_cb.assert_called_with(self.token, self.query_id, "Proposta descartada.")
        mock_send_msg.assert_called_once()
        self.assertIn("descartada", mock_send_msg.call_args[0][2])


if __name__ == "__main__":
    unittest.main()
