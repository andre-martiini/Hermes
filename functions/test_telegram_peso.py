"""Peso pelo Telegram (incidente de 28 e 30/09/2026).

O bot respondeu "peso registrado" duas vezes, por texto e por áudio, sem chamar
ferramenta nenhuma, e nada foi gravado em `health_weights`. Agora o peso é
gravado sem LLM pela mesma escrita do `registrar_saude` do MCP, e a resposta
sai de `verificacao.montar_confirmacao`, a partir do valor relido. Quando o
Gemini usa a ferramenta `registrar_peso`, quem monta a resposta é o código.
"""

import json
import unittest
from unittest import mock

import telegram_message_deterministic as tmd
import telegram_utils as tu
from test_registrar_saude import _Db
from tools import registrar_saude as rs

HOJE_FIXO = "2026-10-01"


def _pesos(db):
    return list(db.cols[rs.COL_PESOS].dados.values()) if rs.COL_PESOS in db.cols else []


class TestReconhecePeso(unittest.TestCase):
    def test_formas_aceitas_gravam_o_valor(self):
        casos = [("peso 94,4", 94.4), ("Peso 94,2", 94.2), ("pesei 94.4", 94.4), ("94,4 kg", 94.4),
                 ("94,4kg", 94.4), ("Peso de 94,3 kg.", 94.3), ("peso: 94,4 kg hoje em jejum", 94.4),
                 ("Meu peso hoje é 94,3", 94.3), ("registrar peso 95", 95.0), ("pesagem 94,45", 94.45),
                 ("estou pesando 94,4", 94.4), ("estou com 94,4 kg", 94.4), ("tô com 94,1kg", 94.1)]
        for texto, valor in casos:
            with self.subTest(texto=texto):
                db = _Db()
                resposta = tu._try_register_weight(db, texto)
                self.assertIn("Peso registrado", resposta or "")
                self.assertEqual([p["weight"] for p in _pesos(db)], [valor])

    def test_mensagens_que_nao_sao_registro_seguem_para_o_modelo(self):
        for texto in ("qual foi meu peso ontem?", "peso", "94,4", "comprei 2 kg de carne",
                      "peso 94 e minha meta é 90", "caminhada 2.5", "meu peso está estranho",
                      "estou com 94,4", "estou com 3 kg de roupa pra lavar", "", None):
            with self.subTest(texto=texto):
                db = _Db()
                self.assertIsNone(tu._try_register_weight(db, texto))
                self.assertEqual(_pesos(db), [])

    def test_fora_da_faixa_avisa_e_nao_grava(self):
        for texto in ("peso 937", "peso 12", "peso 1200"):
            with self.subTest(texto=texto):
                db = _Db()
                resposta = tu._try_register_weight(db, texto)
                self.assertIn("fora da faixa", resposta)
                self.assertIn("confira o valor", resposta)
                self.assertNotIn("Peso registrado", resposta)
                self.assertEqual(_pesos(db), [])


@mock.patch.object(rs, "hoje_brasilia", return_value=HOJE_FIXO)
class TestDataExplicita(unittest.TestCase):
    def test_datas_no_texto_valem_para_o_registro(self, _hoje):
        casos = [("pesei 94,4 ontem", "2026-09-30", 94.4), ("ontem peso 94,2", "2026-09-30", 94.2),
                 ("peso 94,2 anteontem", "2026-09-29", 94.2), ("peso 94,2 dia 28", "2026-09-28", 94.2),
                 ("dia 1 peso 94,6", "2026-10-01", 94.6), ("28/09 peso 94,2", "2026-09-28", 94.2),
                 ("peso 94,2 no dia 28/9/2026", "2026-09-28", 94.2)]
        for texto, dia, valor in casos:
            with self.subTest(texto=texto):
                db = _Db()
                resposta = tu._try_register_weight(db, texto)
                self.assertEqual(_pesos(db), [{"date": dia, "weight": valor}])
                self.assertIn(f"em {dia[8:10]}/{dia[5:7]}/{dia[:4]}", resposta)

    def test_sem_data_vale_hoje(self, _hoje):
        db = _Db()
        tu._try_register_weight(db, "peso 94,4")
        self.assertEqual(_pesos(db), [{"date": HOJE_FIXO, "weight": 94.4}])

    def test_data_impossivel_ou_duas_datas_nao_gravam(self, _hoje):
        for texto in ("peso 94,4 dia 31", "peso 94,4 31/02", "peso 94,4 ontem dia 28"):
            with self.subTest(texto=texto):
                db = _Db()
                resposta = tu._try_register_weight(db, texto)
                self.assertIn("Não registrei o peso", resposta)
                self.assertEqual(_pesos(db), [])

    def test_data_no_futuro_nao_grava(self, _hoje):
        db = _Db()
        resposta = tu._try_register_weight(db, "peso 94,4 28/12")
        self.assertIn("futuro", resposta)
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
        resposta = tu._try_register_weight(db, "peso 94,0")
        self.assertEqual([p["weight"] for p in _pesos(db)], [94.0])
        self.assertIn("94 kg", resposta)


class TestSoConfirmaOQueFoiGravado(unittest.TestCase):
    def test_falha_ao_gravar_avisa(self):
        db = _Db()
        with mock.patch.object(rs, "_gravar_por_data", side_effect=RuntimeError("firestore fora")):
            resposta = tu._try_register_weight(db, "peso 94,4")
        self.assertIn("Não consegui registrar o peso", resposta)
        self.assertIn("Nada foi gravado", resposta)
        self.assertNotIn("Peso registrado", resposta)

    def test_gravacao_que_nao_aparece_na_releitura_nao_e_confirmada(self):
        db = _Db()
        with mock.patch.object(rs, "_gravar_por_data", return_value=f"{rs.COL_PESOS}/sumiu"):
            resposta = tu._try_register_weight(db, "peso 94,4")
        self.assertIn("não aparece", resposta)
        self.assertNotIn("Peso registrado", resposta)

    def test_releitura_com_valor_diferente_nao_e_confirmada(self):
        def grava_outro_valor(db, colecao, dia, campo, valor):
            db.collection(colecao).dados["x"] = {"date": dia, campo: 90.0}
            return f"{colecao}/x"

        db = _Db()
        with mock.patch.object(rs, "_gravar_por_data", side_effect=grava_outro_valor):
            resposta = tu._try_register_weight(db, "peso 94,4")
        self.assertIn("não confere", resposta)
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

    def test_caminhada_continua_antes_do_peso(self):
        with mock.patch.object(tmd, "_try_register_walk_block", return_value="Caminhada registrada") as walk, \
                mock.patch.object(tmd, "_try_register_weight") as peso, \
                mock.patch.object(tmd, "_send_telegram_session_message") as enviar:
            tratada = tmd.try_deterministic_reply(_Db(), "tok", "123", "caminhada 2.5", {}, "gk", "texto",
                                                  "masculina", {}, mock.Mock())
        self.assertTrue(tratada)
        walk.assert_called_once()
        peso.assert_not_called()
        self.assertEqual(enviar.call_args.args[3], "Caminhada registrada")

    def _patches_do_handler(self, **extras):
        patches = {
            "_get_api_keys": mock.Mock(return_value={"gemini_api_key": "gk", "telegram_bot_token": "tok"}),
            "_get_session": mock.Mock(return_value={}),
            "_ensure_copilot_session": mock.Mock(return_value="sessao"),
            "_save_session": mock.Mock(),
            "try_deterministic_reply": mock.Mock(return_value=False),
            "_cached_doc_get": mock.Mock(return_value=mock.Mock(exists=False)),
            "carregar_areas_tematicas_validas": mock.Mock(return_value=["GERAL"]),
            "_load_copilot_session_history": mock.Mock(return_value=[]),
            "_send_telegram_typing": mock.Mock(),
            "_send_telegram_session_message": mock.Mock(return_value=None),
            "_delete_telegram_message": mock.Mock(),
            "_persist_copilot_message": mock.Mock(),
        }
        patches.update(extras)
        return patches

    def test_audio_transcrito_grava_sem_passar_pelo_gemini(self):
        import telegram_handlers_core as thc

        db = _Db()
        patches = self._patches_do_handler(
            _load_telegram_media_bytes=mock.Mock(return_value=b"ogg"),
            _transcribe_audio_bytes=mock.Mock(return_value="Peso de 94,3 kg."),
        )
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

    def test_turno_do_gemini_responde_com_o_valor_relido_e_nao_com_o_texto_do_modelo(self):
        import telegram_handlers_core as thc

        def gemini_que_exagera(**kw):
            kw["function_map"]["registrar_peso"](94.5)
            kw["perf_state"].setdefault("tool_calls", []).append({"name": "registrar_peso"})
            return "Prontinho, registrei 99 kg pra você!"

        db = _Db()
        patches = self._patches_do_handler(_run_gemini_turn=mock.Mock(side_effect=gemini_que_exagera))
        with mock.patch.multiple(thc, **patches):
            thc._process_telegram_message(db, {"chat_id": "123", "text": "anota aí: noventa e quatro e meio"})
        enviada = patches["_send_telegram_session_message"].call_args.args[3]
        self.assertIn("Peso registrado: 94,5 kg", enviada)
        self.assertNotIn("99 kg", enviada)
        self.assertEqual([p["weight"] for p in _pesos(db)], [94.5])

    def test_turno_do_gemini_com_falha_nao_deixa_passar_registrei(self):
        import telegram_handlers_core as thc

        def gemini_que_mente(**kw):
            kw["function_map"]["registrar_peso"](940)
            kw["perf_state"].setdefault("tool_calls", []).append({"name": "registrar_peso"})
            return "Registrei seu peso!"

        db = _Db()
        patches = self._patches_do_handler(_run_gemini_turn=mock.Mock(side_effect=gemini_que_mente))
        with mock.patch.multiple(thc, **patches):
            thc._process_telegram_message(db, {"chat_id": "123", "text": "anota meu peso, novecentos e quarenta"})
        enviada = patches["_send_telegram_session_message"].call_args.args[3]
        self.assertIn("Não consegui registrar o peso", enviada)
        self.assertNotIn("Registrei", enviada)
        self.assertEqual(_pesos(db), [])


class TestRespostaComResultadosVerificados(unittest.TestCase):
    def _res(self, estado="verificado", peso=94.4):
        from verificacao import ResultadoOperacao

        if estado == "verificado":
            return ResultadoOperacao("verificado", "registrar_peso", "health_weights/x",
                                     valor_relido={"date": "2026-10-01", "weight": peso}).to_dict()
        return ResultadoOperacao("falhou", "registrar_peso", "health_weights", motivo="sem rede").to_dict()

    def test_turno_so_de_registro_responde_so_com_o_codigo(self):
        texto = tu._resposta_com_resultados_verificados([self._res()], "Registrei 95 kg!", ["registrar_peso"])
        self.assertEqual(texto, "⚖️ Peso registrado: 94,4 kg em 01/10/2026.")

    def test_turno_com_outras_ferramentas_mantem_o_texto_do_modelo_depois(self):
        texto = tu._resposta_com_resultados_verificados(
            [self._res()], "Sua agenda de hoje tem 2 reuniões.", ["registrar_peso", "consultar_agenda"])
        self.assertTrue(texto.startswith("⚖️ Peso registrado: 94,4 kg"))
        self.assertTrue(texto.endswith("Sua agenda de hoje tem 2 reuniões."))

    def test_falha_vira_aviso(self):
        texto = tu._resposta_com_resultados_verificados([self._res("falhou")], "Registrei!", ["registrar_peso"])
        self.assertEqual(texto, "⚠️ Não consegui registrar o peso: sem rede")


class TestFerramentaDoGemini(unittest.TestCase):
    def test_registrar_peso_devolve_resultado_verificado_e_avisa_o_handler(self):
        import telegram_message_tools as tmt

        db, sessao = _Db(), {}
        ferramentas = {f.__name__: f for f in tmt.build_telegram_tool_closures(
            db, sessao, "geral", None, None, False, False, ["GERAL"])}
        resultado = json.loads(ferramentas["registrar_peso"](94.4))
        self.assertEqual(resultado["estado"], "verificado")
        self.assertTrue(resultado["confirmacao"].startswith("Peso registrado: 94,4 kg"))
        self.assertEqual([p["weight"] for p in _pesos(db)], [94.4])
        self.assertEqual(len(sessao["_resultados_verificados"]), 1)

    def test_prompt_proibe_confirmar_registro_sem_ferramenta(self):
        texto = tu._build_system_instruction_guarded_v2("", "", "geral", None)
        self.assertIn("REGISTROS: so diga que registrou", texto)
        self.assertIn("registrar_peso", texto)


if __name__ == "__main__":
    unittest.main()
