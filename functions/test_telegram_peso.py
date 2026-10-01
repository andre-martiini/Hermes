"""Peso pelo Telegram (incidente de 28 e 30/09/2026).

O bot respondeu "peso registrado" duas vezes, por texto e por áudio, sem chamar
ferramenta nenhuma, e nada foi gravado em `health_weights`. Agora o peso é
gravado sem LLM pelo mesmo caminho do `registrar_saude` do MCP, e a confirmação
só sai depois de reler o que ficou gravado.
"""

import json
import unittest
from unittest import mock

import telegram_message_deterministic as tmd
import telegram_utils as tu
from test_registrar_saude import _Db
from tools import registrar_saude as rs


def _pesos(db):
    return list(db.cols[rs.COL_PESOS].dados.values()) if rs.COL_PESOS in db.cols else []


class TestReconhecePeso(unittest.TestCase):
    def test_formas_aceitas_gravam_o_valor(self):
        casos = [("peso 94,4", 94.4), ("Peso 94,2", 94.2), ("pesei 94.4", 94.4), ("94,4 kg", 94.4),
                 ("94,4kg", 94.4), ("Peso de 94,3 kg.", 94.3), ("peso: 94,4 kg hoje em jejum", 94.4),
                 ("Meu peso hoje é 94,3", 94.3), ("registrar peso 95", 95.0), ("pesagem 94,45", 94.45)]
        for texto, valor in casos:
            with self.subTest(texto=texto):
                db = _Db()
                resposta = tu._try_register_weight(db, texto)
                self.assertIn("Peso registrado", resposta or "")
                self.assertEqual([p["weight"] for p in _pesos(db)], [valor])

    def test_mensagens_que_nao_sao_registro_seguem_para_o_modelo(self):
        for texto in ("qual foi meu peso ontem?", "peso", "94,4", "comprei 2 kg de carne",
                      "peso 94 e minha meta é 90", "caminhada 2.5", "", None):
            with self.subTest(texto=texto):
                db = _Db()
                self.assertIsNone(tu._try_register_weight(db, texto))
                self.assertEqual(_pesos(db), [])

    def test_fora_da_faixa_avisa_e_nao_grava(self):
        for texto in ("peso 937", "peso 12"):
            with self.subTest(texto=texto):
                db = _Db()
                resposta = tu._try_register_weight(db, texto)
                self.assertIn("fora da faixa", resposta)
                self.assertNotIn("Peso registrado", resposta)
                self.assertEqual(_pesos(db), [])


class TestGravaNoFormatoDaWeb(unittest.TestCase):
    def test_grava_data_de_hoje_e_peso(self):
        db = _Db()
        resposta = tu._try_register_weight(db, "peso 94,4")
        self.assertEqual(_pesos(db), [{"date": rs.hoje_brasilia(), "weight": 94.4}])
        self.assertIn("94,4 kg", resposta)

    def test_mesma_data_atualiza_sem_duplicar(self):
        db = _Db()
        tu._try_register_weight(db, "peso 94,4")
        tu._try_register_weight(db, "peso 94,1")
        self.assertEqual([p["weight"] for p in _pesos(db)], [94.1])


class TestSoConfirmaOQueFoiGravado(unittest.TestCase):
    def test_falha_ao_gravar_avisa(self):
        db = _Db()
        with mock.patch.object(rs, "_gravar_por_data", side_effect=RuntimeError("firestore fora")):
            resposta = tu._try_register_weight(db, "peso 94,4")
        self.assertIn("Não consegui gravar o peso", resposta)
        self.assertNotIn("Peso registrado", resposta)

    def test_gravacao_que_nao_aparece_na_releitura_nao_e_confirmada(self):
        db = _Db()
        with mock.patch.object(rs, "_gravar_por_data"):
            resposta = tu._try_register_weight(db, "peso 94,4")
        self.assertIn("não aparece", resposta)
        self.assertNotIn("Peso registrado", resposta)


class TestCaminhosDoTelegram(unittest.TestCase):
    def test_texto_e_tratado_antes_do_gemini(self):
        db = _Db()
        persistir = mock.Mock()
        with mock.patch.object(tmd, "_try_register_walk_block", return_value=None), \
                mock.patch.object(tmd, "_send_telegram_session_message") as enviar:
            tratada = tmd.try_deterministic_reply(db, "tok", "123", "Peso 94,2", {}, "gk", "texto",
                                                  "masculina", {}, persistir)
        self.assertTrue(tratada)
        self.assertIn("Peso registrado", enviar.call_args.args[3])
        persistir.assert_called_once()
        self.assertEqual([p["weight"] for p in _pesos(db)], [94.2])

    def test_audio_transcrito_grava_sem_passar_pelo_gemini(self):
        import telegram_handlers_core as thc

        db = _Db()
        patches = {
            "_get_api_keys": mock.Mock(return_value={"gemini_api_key": "gk", "telegram_bot_token": "tok"}),
            "_get_session": mock.Mock(return_value={}),
            "_ensure_copilot_session": mock.Mock(return_value="sessao"),
            "_save_session": mock.Mock(),
            "try_deterministic_reply": mock.Mock(return_value=False),
            "_cached_doc_get": mock.Mock(return_value=mock.Mock(exists=False)),
            "carregar_areas_tematicas_validas": mock.Mock(return_value=["GERAL"]),
            "_load_copilot_session_history": mock.Mock(return_value=[]),
            "_load_telegram_media_bytes": mock.Mock(return_value=b"ogg"),
            "_transcribe_audio_bytes": mock.Mock(return_value="Peso de 94,3 kg."),
            "_send_telegram_typing": mock.Mock(),
            "_send_telegram_session_message": mock.Mock(),
            "_persist_copilot_message": mock.Mock(),
        }
        gemini = mock.Mock(side_effect=AssertionError("o Gemini não deveria ser chamado"))
        with mock.patch.multiple(thc, **patches), mock.patch("google.genai.Client", gemini):
            thc._process_telegram_message(db, {
                "chat_id": "123", "text": "",
                "audio_info": {"mime_type": "audio/ogg"}, "media_bytes_b64": "b2dn",
            })
        enviada = patches["_send_telegram_session_message"].call_args.args[3]
        self.assertIn("Peso registrado", enviada)
        self.assertEqual([p["weight"] for p in _pesos(db)], [94.3])
        gemini.assert_not_called()


class TestFerramentaDoGemini(unittest.TestCase):
    def test_registrar_peso_grava_pelo_registrar_saude(self):
        import telegram_message_tools as tmt

        db = _Db()
        ferramentas = {f.__name__: f for f in tmt.build_telegram_tool_closures(
            db, {}, "geral", None, None, False, False, ["GERAL"])}
        resultado = json.loads(ferramentas["registrar_peso"](94.4))
        self.assertEqual(resultado["status"], "completed")
        self.assertEqual([p["weight"] for p in _pesos(db)], [94.4])

    def test_prompt_proibe_confirmar_registro_sem_ferramenta(self):
        texto = tu._build_system_instruction_guarded_v2("", "", "geral", None)
        self.assertIn("REGISTROS: so diga que registrou", texto)
        self.assertIn("registrar_peso", texto)


if __name__ == "__main__":
    unittest.main()
