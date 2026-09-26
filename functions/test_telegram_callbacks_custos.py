"""Testes do botão "Ver detalhes" do relatório diário de custos.

Cobre: o callback `custos:det:<dia>` / `custos:res:<dia>` (telegram_callbacks_custos),
o roteamento pelo dispatcher de telegram_handlers_core e o envio do resumo com
teclado + gravação em `system_reports` (cost_report.relatorio_diario_custos).
"""

import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cost_report
import telegram_callbacks_custos as tcc


class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _Doc:
    def __init__(self, store, key):
        self.store, self.key = store, key

    def get(self):
        return _Snap(self.store.get(self.key))

    def set(self, data, merge=False):
        self.store[self.key] = dict(data)


class _Db:
    def __init__(self, store=None):
        self.store = store if store is not None else {}

    def collection(self, name):
        db = self

        class _Col:
            def document(self, doc_id):
                return _Doc(db.store, f"{name}/{doc_id}")

        return _Col()


RELATORIO = {
    "system_reports/custos_2026-09-25": {
        "resumo": "💰 <b>Custos do Gaspar — 25/09</b>\nOntem: R$ 10,16",
        "detalhe": "💰 <b>Custos do Gaspar — 25/09/2026</b>\n☁️ <b>GCP 25/09</b>: R$ 10,16",
    }
}


def _call(db, data, message_id=77):
    message = {"chat": {"id": 123}, "message_id": message_id}
    return tcc.handle(db, "tok", "q1", "123", data, message, {}, "sess", None, None, None)


@patch("telegram_callbacks_custos._answer_callback_query")
@patch("telegram_callbacks_custos._edit_message_text", return_value=True)
class HandleTest(unittest.TestCase):
    def test_ver_detalhes_edita_para_o_detalhe_com_botao_resumo(self, mock_edit, mock_answer):
        tratou = _call(_Db(dict(RELATORIO)), "custos:det:2026-09-25")
        self.assertTrue(tratou)
        mock_edit.assert_called_once()
        token, chat_id, message_id, texto, teclado = mock_edit.call_args[0]
        self.assertEqual((token, chat_id, message_id), ("tok", "123", 77))
        self.assertIn("GCP 25/09", texto)
        self.assertEqual(teclado, [[{"text": "↩️ Resumo", "callback_data": "custos:res:2026-09-25"}]])
        mock_answer.assert_called_once_with("tok", "q1")

    def test_resumo_volta_para_o_resumo_com_botao_detalhes(self, mock_edit, mock_answer):
        _call(_Db(dict(RELATORIO)), "custos:res:2026-09-25")
        texto, teclado = mock_edit.call_args[0][3], mock_edit.call_args[0][4]
        self.assertTrue(texto.endswith("Ontem: R$ 10,16"))
        self.assertEqual(teclado, [[{"text": "📋 Ver detalhes", "callback_data": "custos:det:2026-09-25"}]])

    def test_relatorio_ausente_avisa_sem_editar(self, mock_edit, mock_answer):
        tratou = _call(_Db({}), "custos:det:2026-09-01")
        self.assertTrue(tratou)
        mock_edit.assert_not_called()
        aviso = mock_answer.call_args[0][2]
        self.assertIn("2026-09-01", aviso)
        self.assertIn("não está mais disponível", aviso)

    def test_callback_malformado_e_consumido_com_aviso(self, mock_edit, mock_answer):
        self.assertTrue(_call(_Db(dict(RELATORIO)), "custos:det:ontem"))
        mock_edit.assert_not_called()
        self.assertEqual(mock_answer.call_args[0][2], "Botão inválido.")

    def test_outros_prefixos_nao_sao_tratados(self, mock_edit, mock_answer):
        self.assertFalse(_call(_Db(dict(RELATORIO)), "merge_confirm:abc"))
        mock_edit.assert_not_called()
        mock_answer.assert_not_called()

    def test_falha_na_edicao_avisa(self, mock_edit, mock_answer):
        mock_edit.return_value = False
        _call(_Db(dict(RELATORIO)), "custos:det:2026-09-25")
        self.assertEqual(mock_answer.call_args[0][2], "Não consegui atualizar a mensagem.")


class EditMessageTextTest(unittest.TestCase):
    @patch("telegram_callbacks_custos._requests.post")
    def test_envia_html_com_teclado(self, mock_post):
        mock_post.return_value = MagicMock(ok=True, text="{}")
        ok = tcc._edit_message_text("tok", "123", 77, "<b>oi</b>", [[{"text": "x", "callback_data": "y"}]])
        self.assertTrue(ok)
        url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
        self.assertTrue(url.endswith("/editMessageText"))
        self.assertEqual(kwargs["json"]["parse_mode"], "HTML")
        self.assertEqual(kwargs["json"]["message_id"], 77)
        self.assertEqual(kwargs["json"]["reply_markup"], {"inline_keyboard": [[{"text": "x", "callback_data": "y"}]]})

    @patch("telegram_callbacks_custos._requests.post")
    def test_mensagem_nao_modificada_conta_como_sucesso(self, mock_post):
        mock_post.return_value = MagicMock(ok=False, status_code=400, text="Bad Request: message is not modified")
        self.assertTrue(tcc._edit_message_text("tok", "123", 77, "a", []))
        self.assertEqual(mock_post.call_count, 1)

    @patch("telegram_callbacks_custos._requests.post")
    def test_html_recusado_tenta_texto_puro(self, mock_post):
        mock_post.side_effect = [
            MagicMock(ok=False, status_code=400, text="can't parse entities"),
            MagicMock(ok=True, text="{}"),
        ]
        self.assertTrue(tcc._edit_message_text("tok", "123", 77, "<b>a &amp; b</b>", []))
        retry = mock_post.call_args_list[1][1]["json"]
        self.assertNotIn("parse_mode", retry)
        self.assertEqual(retry["text"], "a & b")


class DispatcherTest(unittest.TestCase):
    """O dispatcher central entrega `custos:` ao módulo novo."""

    @patch("telegram_callbacks_custos._answer_callback_query")
    @patch("telegram_callbacks_custos._edit_message_text", return_value=True)
    @patch("telegram_handlers_core._persist_copilot_message")
    @patch("telegram_handlers_core._save_session")
    @patch("telegram_handlers_core._ensure_copilot_session", return_value="copilot-sess-1")
    @patch("telegram_handlers_core._get_session", return_value={})
    @patch("telegram_handlers_core._get_allowed_chat_id", return_value=None)
    def test_roteia_prefixo_custos(self, _allowed, _get_sess, _ensure, _save, _persist, mock_edit, mock_answer):
        from hermes_core_logic import _handle_telegram_callback

        cb = {
            "id": "q1",
            "data": "custos:det:2026-09-25",
            "message": {"chat": {"id": 123}, "message_id": 77},
            "from": {"id": 1},
        }
        resp = _handle_telegram_callback(_Db(dict(RELATORIO)), "tok", cb)
        self.assertEqual(resp.status_code, 200)
        mock_edit.assert_called_once()
        self.assertIn("GCP 25/09", mock_edit.call_args[0][3])


class EnvioRelatorioTest(unittest.TestCase):
    """relatorio_diario_custos: grava os dois textos e envia o resumo com botão."""

    TEXTOS = {"dia": "2026-09-25", "resumo": "RESUMO", "detalhe": "DETALHE"}

    def _run(self, db, salvar_side_effect=None):
        fake_main = types.ModuleType("main")
        fake_main.get_db = lambda: db
        fake_main._resolve_default_telegram_chat_id = lambda _db: "123"
        fake_utils = types.ModuleType("telegram_utils")
        fake_utils._get_telegram_token = lambda _db: "tok"
        fake_utils._send_telegram_message = MagicMock()
        fake_utils._send_telegram_message_with_keyboard = MagicMock()
        fake_fs = MagicMock()
        fake_fs.SERVER_TIMESTAMP = "TS"
        patches = [
            patch.dict(sys.modules, {"main": fake_main, "telegram_utils": fake_utils}),
            patch("firebase_admin.firestore", fake_fs, create=True),
            patch.object(cost_report, "gerar_relatorios_custos", return_value=dict(self.TEXTOS)),
        ]
        if salvar_side_effect is not None:
            patches.append(patch.object(cost_report, "salvar_relatorio", side_effect=salvar_side_effect))
        for p in patches:
            p.start()
        try:
            fn = getattr(cost_report.relatorio_diario_custos, "__wrapped__", cost_report.relatorio_diario_custos)
            fn(None)
        finally:
            for p in reversed(patches):
                p.stop()
        return fake_utils

    def test_grava_e_envia_resumo_com_botao(self):
        db = _Db({})
        utils = self._run(db)
        doc = db.store["system_reports/custos_2026-09-25"]
        self.assertEqual((doc["resumo"], doc["detalhe"], doc["dia"]), ("RESUMO", "DETALHE", "2026-09-25"))
        self.assertIn("created_at", doc)
        utils._send_telegram_message_with_keyboard.assert_called_once_with(
            "tok", "123", "RESUMO",
            [[{"text": "📋 Ver detalhes", "callback_data": "custos:det:2026-09-25"}]],
        )
        utils._send_telegram_message.assert_not_called()

    def test_sem_gravar_manda_o_detalhe_sem_botao(self):
        utils = self._run(_Db({}), salvar_side_effect=RuntimeError("firestore fora"))
        utils._send_telegram_message.assert_called_once_with("tok", "123", "DETALHE")
        utils._send_telegram_message_with_keyboard.assert_not_called()


if __name__ == "__main__":
    unittest.main()
