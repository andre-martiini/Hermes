"""Testes do perfil pessoal: espelho semanal no Telegram, correção via botão
"✏️ Corrigir", inclusão da correção na consolidação seguinte e o
`perfil_pessoal` de `obter_estado_atual`.

Cobre: personal_diary (build_mirror_message, mirror_keyboard,
_build_personality_prompt, registrar_ajuste_personalidade,
consolidar_personalidade), telegram_callbacks_perfil (perfil:fix/perfil:ok e o
roteamento pelo dispatcher), telegram_message_deterministic (captura da
próxima mensagem livre) e tools.hermes_tools.obter_estado_atual.
"""

import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import personal_diary as pd
import telegram_callbacks_perfil as tcp
import telegram_message_deterministic as tmd


# --------------------------------------------------------------------------- #
# Firestore falso (get/set com merge profundo)                                 #
# --------------------------------------------------------------------------- #

def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class _Snap:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _Doc:
    def __init__(self, store, key):
        self.store, self.key = store, key

    def get(self):
        return _Snap(self.key.split("/")[-1], self.store.get(self.key))

    def set(self, data, merge=False):
        if merge and self.key in self.store:
            self.store[self.key] = _deep_merge(self.store[self.key], data)
        else:
            self.store[self.key] = dict(data)


class _Db:
    def __init__(self, store=None):
        self.store = store if store is not None else {}

    def collection(self, name):
        db = self

        class _Col:
            def document(self, doc_id):
                return _Doc(db.store, f"{name}/{doc_id}")

            def limit(self, _n):
                return self

            def stream(self):
                return [
                    _Snap(k.split("/", 1)[1], v)
                    for k, v in db.store.items() if k.startswith(f"{name}/")
                ]

        return _Col()


PERFIL_ANTIGO = {
    "resumo_narrativo": "Pessoa metódica.",
    "gatilhos_de_estresse": ["Reuniões longas", "Prazos apertados"],
    "fontes_de_energia": ["Caminhada"],
    "rotinas": ["Acorda cedo"],
}
PERFIL_NOVO = {
    "resumo_narrativo": "Pessoa metódica que protege as manhãs <foco>.",
    "gatilhos_de_estresse": ["prazos apertados", "Interrupções no WhatsApp"],
    "fontes_de_energia": ["Caminhada", "Tocar violão"],
    "rotinas": ["Acorda cedo"],
}


# --------------------------------------------------------------------------- #
# Mensagem do espelho                                                          #
# --------------------------------------------------------------------------- #

class MirrorMessageTest(unittest.TestCase):
    def test_titulo_resumo_e_mudancas(self):
        texto = pd.build_mirror_message(PERFIL_NOVO, PERFIL_ANTIGO)
        linhas = texto.split("\n")
        self.assertTrue(4 <= len(linhas) <= 6, linhas)
        self.assertEqual(linhas[0], "🪞 <b>O que percebi em você esta semana</b>")
        # HTML escapado no resumo.
        self.assertIn("&lt;foco&gt;", linhas[1])
        entrou = next(l for l in linhas if l.startswith("➕"))
        saiu = next(l for l in linhas if l.startswith("➖"))
        self.assertIn("Interrupções no WhatsApp", entrou)
        self.assertIn("Tocar violão", entrou)
        self.assertIn("Reuniões longas", saiu)
        # Mesma ideia com caixa diferente não conta como mudança.
        self.assertNotIn("prazos apertados", entrou.lower().replace("interrupções", ""))
        self.assertNotIn("Prazos apertados", saiu)
        self.assertIn("impressões, não fatos", linhas[-1])

    def test_primeira_leitura_sem_versao_anterior(self):
        texto = pd.build_mirror_message(PERFIL_NOVO, None)
        self.assertIn("Primeira leitura", texto)
        self.assertNotIn("➕", texto)
        self.assertEqual(len(texto.split("\n")), 4)

    def test_sem_mudancas(self):
        texto = pd.build_mirror_message(PERFIL_ANTIGO, dict(PERFIL_ANTIGO))
        self.assertIn("Sem mudança", texto)
        self.assertNotIn("➕", texto)
        self.assertNotIn("➖", texto)

    def test_limita_itens_por_linha(self):
        novo = dict(PERFIL_ANTIGO, fontes_de_energia=["a", "b", "c", "d", "e"])
        texto = pd.build_mirror_message(novo, {"fontes_de_energia": []})
        self.assertIn("energia: a; b; c (+2)", texto)

    def test_teclado_corrigir_e_esta_certo(self):
        self.assertEqual(pd.mirror_keyboard(), [[
            {"text": "✏️ Corrigir", "callback_data": "perfil:fix"},
            {"text": "👍 Está certo", "callback_data": "perfil:ok"},
        ]])


# --------------------------------------------------------------------------- #
# Correção direta e prompt                                                     #
# --------------------------------------------------------------------------- #

class AjusteTest(unittest.TestCase):
    def setUp(self):
        p = patch.dict(os.environ, {"HERMES_DEFAULT_USER_ID": "u1"})
        p.start()
        self.addCleanup(p.stop)

    def test_registra_com_data_e_preserva_resto_do_perfil(self):
        db = _Db({"usuarios/u1": {"ai_profile": {"personalidade": PERFIL_ANTIGO,
                                                  "personalidade_atualizada_em": "2026-09-20T01:00:00+00:00"}}})
        resposta = pd.registrar_ajuste_personalidade(db, "  Não me estresso com reuniões, e sim com retrabalho.  ")
        self.assertEqual(resposta, "Anotado — entra na próxima leitura de domingo.")
        ai = db.store["usuarios/u1"]["ai_profile"]
        self.assertEqual(ai["personalidade"], PERFIL_ANTIGO)
        self.assertEqual(len(ai["personalidade_ajustes"]), 1)
        ajuste = ai["personalidade_ajustes"][0]
        self.assertEqual(ajuste["texto"], "Não me estresso com reuniões, e sim com retrabalho.")
        self.assertEqual(ajuste["versao_perfil"], "2026-09-20T01:00:00+00:00")
        self.assertTrue(ajuste["em"])

    def test_lista_tem_teto(self):
        antigos = [{"texto": f"c{i}", "em": "2026-01-01"} for i in range(pd.MAX_AJUSTES_PERSONALIDADE)]
        db = _Db({"usuarios/u1": {"ai_profile": {"personalidade_ajustes": antigos}}})
        pd.registrar_ajuste_personalidade(db, "nova")
        ajustes = db.store["usuarios/u1"]["ai_profile"]["personalidade_ajustes"]
        self.assertEqual(len(ajustes), pd.MAX_AJUSTES_PERSONALIDADE)
        self.assertEqual(ajustes[-1]["texto"], "nova")
        self.assertEqual(ajustes[0]["texto"], "c1")

    def test_texto_vazio_nao_grava(self):
        db = _Db({"usuarios/u1": {"ai_profile": {}}})
        self.assertIn("Não recebi", pd.registrar_ajuste_personalidade(db, "   "))
        self.assertNotIn("personalidade_ajustes", db.store["usuarios/u1"]["ai_profile"])

    def test_prompt_traz_correcoes_como_sinal_mais_forte(self):
        correcoes = pd._format_ajustes_personalidade([
            {"texto": "Retrabalho me cansa, reunião não.", "em": "2026-09-21T10:00:00+00:00"},
            "lixo", {"texto": ""},
        ])
        self.assertEqual(correcoes, "- [2026-09-21] Retrabalho me cansa, reunião não.")
        prompt = pd._build_personality_prompt(PERFIL_ANTIGO, "- pedido do diário", "[2026-09-20]\ntexto", correcoes)
        self.assertIn("CORREÇÕES DIRETAS DO USUÁRIO", prompt)
        self.assertIn("MAIS FORTE", prompt)
        self.assertIn("Retrabalho me cansa", prompt)
        self.assertLess(prompt.index("CORREÇÕES DIRETAS"), prompt.index("AJUSTES QUE O PRÓPRIO USUÁRIO"))
        self.assertIn("- pedido do diário", prompt)

    def test_prompt_sem_correcoes(self):
        prompt = pd._build_personality_prompt(None, "", "x")
        self.assertIn("(nenhuma correção direta)", prompt)
        self.assertIn("(nenhum perfil anterior)", prompt)

    def test_formato_limita_quantidade(self):
        ajustes = [{"texto": f"c{i}"} for i in range(15)]
        linhas = pd._format_ajustes_personalidade(ajustes).split("\n")
        self.assertEqual(len(linhas), pd.MAX_AJUSTES_NO_PROMPT)
        self.assertEqual(linhas[-1], "- c14")


# --------------------------------------------------------------------------- #
# consolidar_personalidade de ponta a ponta (com fakes)                        #
# --------------------------------------------------------------------------- #

class ConsolidarTest(unittest.TestCase):
    def _db(self, enabled=True, perfil=PERFIL_ANTIGO, ajustes=None):
        from zoneinfo import ZoneInfo
        hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        store = {
            "usuarios/u1": {"ai_profile": {"personalidade": perfil,
                                           "personalidade_ajustes": ajustes or []}},
        }
        for i in range(1, 4):
            d = (hoje - timedelta(days=i)).strftime("%Y-%m-%d")
            store[f"diario_pessoal/{d}"] = {"data": d, "texto": f"diário {d}",
                                            "ajustes": [{"pedido": f"ajuste {d}"}]}
        return _Db(store), enabled

    def _run(self, db, enabled, resposta_json):
        settings = MagicMock(exists=True)
        settings.to_dict.return_value = {"personal_diary": {"enabled": enabled}}
        keys = MagicMock(exists=True)
        keys.to_dict.return_value = {"gemini_api_key": "k"}
        fake_main = types.ModuleType("main")
        fake_main.get_db = lambda: db
        fake_main._cached_doc_get = lambda _db, col, doc: settings if doc == "settings" else keys
        fake_main.get_genai_module = lambda: MagicMock()
        gerar = MagicMock(return_value=MagicMock(text=resposta_json))
        enviar = MagicMock()
        with patch.dict(sys.modules, {"main": fake_main}), \
                patch.dict(os.environ, {"HERMES_DEFAULT_USER_ID": "u1"}), \
                patch.object(pd, "generate_content_logged", gerar), \
                patch.object(pd, "_enviar_espelho_semanal", enviar):
            fn = getattr(pd.consolidar_personalidade, "__wrapped__", pd.consolidar_personalidade)
            fn(None)
        return gerar, enviar

    def test_grava_perfil_envia_espelho_e_usa_correcoes(self):
        import json
        db, enabled = self._db(ajustes=[{"texto": "Retrabalho me cansa.", "em": "2026-09-21T10:00:00+00:00"}])
        gerar, enviar = self._run(db, enabled, json.dumps(PERFIL_NOVO))

        prompt = gerar.call_args.kwargs["contents"]
        self.assertIn("Retrabalho me cansa.", prompt)
        self.assertIn("ajuste ", prompt)  # ajustes dos diários continuam indo

        ai = db.store["usuarios/u1"]["ai_profile"]
        self.assertEqual(ai["personalidade"], PERFIL_NOVO)
        self.assertEqual(ai["personalidade_historico"][-1]["versao"], PERFIL_ANTIGO)
        enviar.assert_called_once()
        self.assertEqual(enviar.call_args.args[1:], (PERFIL_NOVO, PERFIL_ANTIGO))

    def test_desligado_nao_faz_nada(self):
        db, _ = self._db()
        gerar, enviar = self._run(db, False, "{}")
        gerar.assert_not_called()
        enviar.assert_not_called()

    def test_resposta_invalida_nao_envia_espelho(self):
        db, enabled = self._db()
        gerar, enviar = self._run(db, enabled, "{}")
        gerar.assert_called_once()
        enviar.assert_not_called()
        self.assertEqual(db.store["usuarios/u1"]["ai_profile"]["personalidade"], PERFIL_ANTIGO)

    def test_falha_no_envio_nao_desfaz_o_perfil(self):
        import json
        db, enabled = self._db()
        settings = MagicMock(exists=True)
        settings.to_dict.return_value = {"personal_diary": {"enabled": True}}
        with patch.object(pd, "build_mirror_message", side_effect=RuntimeError("boom")):
            # _enviar_espelho_semanal real, com main/telegram falsos
            fake_main = types.ModuleType("main")
            fake_main.get_db = lambda: db
            keys = MagicMock(exists=True)
            keys.to_dict.return_value = {"gemini_api_key": "k"}
            fake_main._cached_doc_get = lambda _db, col, doc: settings if doc == "settings" else keys
            fake_main.get_genai_module = lambda: MagicMock()
            fake_main._resolve_default_telegram_chat_id = lambda _db: "123"
            with patch.dict(sys.modules, {"main": fake_main}), \
                    patch.dict(os.environ, {"HERMES_DEFAULT_USER_ID": "u1"}), \
                    patch("telegram_utils._get_telegram_token", return_value="tok"), \
                    patch.object(pd, "generate_content_logged",
                                 return_value=MagicMock(text=json.dumps(PERFIL_NOVO))):
                fn = getattr(pd.consolidar_personalidade, "__wrapped__", pd.consolidar_personalidade)
                fn(None)
        self.assertEqual(db.store["usuarios/u1"]["ai_profile"]["personalidade"], PERFIL_NOVO)


class EnviarEspelhoTest(unittest.TestCase):
    def test_envia_html_com_teclado(self):
        fake_main = types.ModuleType("main")
        fake_main._resolve_default_telegram_chat_id = lambda _db: "123"
        with patch.dict(sys.modules, {"main": fake_main}), \
                patch("telegram_utils._get_telegram_token", return_value="tok"), \
                patch("telegram_utils._send_telegram_message_with_keyboard") as enviar:
            self.assertTrue(pd._enviar_espelho_semanal(MagicMock(), PERFIL_NOVO, PERFIL_ANTIGO))
        token, chat_id, texto, teclado = enviar.call_args.args
        self.assertEqual((token, chat_id), ("tok", "123"))
        self.assertTrue(texto.startswith("🪞 <b>O que percebi em você esta semana</b>"))
        self.assertEqual(teclado, pd.mirror_keyboard())

    def test_sem_chat_id_nao_envia(self):
        fake_main = types.ModuleType("main")
        fake_main._resolve_default_telegram_chat_id = lambda _db: None
        with patch.dict(sys.modules, {"main": fake_main}), \
                patch("telegram_utils._send_telegram_message_with_keyboard") as enviar:
            self.assertFalse(pd._enviar_espelho_semanal(MagicMock(), PERFIL_NOVO, None))
        enviar.assert_not_called()


# --------------------------------------------------------------------------- #
# Callbacks perfil:fix / perfil:ok                                             #
# --------------------------------------------------------------------------- #

@patch("telegram_callbacks_perfil._send_telegram_message")
@patch("telegram_callbacks_perfil._save_session")
@patch("telegram_callbacks_perfil._answer_callback_query")
class CallbackTest(unittest.TestCase):
    def _call(self, data, session):
        self.persist = MagicMock()
        return tcp.handle(MagicMock(), "tok", "q1", "123", data, {"message_id": 5}, session,
                          "sess", self.persist, None, None)

    def test_corrigir_marca_sessao_e_pede_texto(self, mock_answer, mock_save, mock_send):
        session = {}
        self.assertTrue(self._call("perfil:fix", session))
        self.assertIn("pending_perfil_ajuste", session)
        datetime.fromisoformat(session["pending_perfil_ajuste"])  # ISO válido
        mock_save.assert_called_once()
        mock_send.assert_called_once()
        self.assertIn("próxima mensagem vira a correção", mock_send.call_args.args[2])
        mock_answer.assert_called_once()

    def test_esta_certo_so_agradece(self, mock_answer, mock_save, mock_send):
        session = {}
        self.assertTrue(self._call("perfil:ok", session))
        self.assertEqual(session, {})
        mock_save.assert_not_called()
        mock_send.assert_not_called()
        self.assertIn("Valeu", mock_answer.call_args.args[2])

    def test_outros_callbacks_nao_sao_tratados(self, mock_answer, mock_save, mock_send):
        self.assertFalse(self._call("diary_ok:2026-09-25", {}))
        mock_answer.assert_not_called()


class DispatcherTest(unittest.TestCase):
    @patch("telegram_callbacks_perfil._send_telegram_message")
    @patch("telegram_callbacks_perfil._save_session")
    @patch("telegram_callbacks_perfil._answer_callback_query")
    @patch("telegram_handlers_core._persist_copilot_message")
    @patch("telegram_handlers_core._save_session")
    @patch("telegram_handlers_core._ensure_copilot_session", return_value="copilot-sess-1")
    @patch("telegram_handlers_core._get_allowed_chat_id", return_value=None)
    def test_roteia_prefixo_perfil(self, _allowed, _ensure, _save_core, _persist, _answer, mock_save, mock_send):
        from hermes_core_logic import _handle_telegram_callback

        session = {}
        cb = {"id": "q1", "data": "perfil:fix",
              "message": {"chat": {"id": 123}, "message_id": 77}, "from": {"id": 1}}
        with patch("telegram_handlers_core._get_session", return_value=session):
            resp = _handle_telegram_callback(_Db(), "tok", cb)
        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_once()
        self.assertIn("pending_perfil_ajuste", session)


# --------------------------------------------------------------------------- #
# Captura da próxima mensagem livre                                            #
# --------------------------------------------------------------------------- #

class CapturaCorrecaoTest(unittest.TestCase):
    def setUp(self):
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
        self.save = mock.patch.object(tmd, "_save_session").start()
        self.send = mock.patch.object(tmd, "_send_telegram_session_message").start()
        self.addCleanup(mock.patch.stopall)
        self.persist = mock.Mock()

    def _responder(self, texto, session):
        return tmd.try_deterministic_reply(
            mock.Mock(), "tok", "123", texto, session, "gk", "texto",
            "masculina", {}, self.persist,
        )

    def test_texto_vira_correcao_e_confirma(self):
        session = {"pending_perfil_ajuste": datetime.now(timezone.utc).isoformat()}
        with mock.patch("personal_diary.registrar_ajuste_personalidade",
                        return_value=pd.AJUSTE_CONFIRMACAO) as registrar:
            tratada = self._responder("Não me estresso com reunião.", session)
        self.assertTrue(tratada)
        registrar.assert_called_once()
        self.assertEqual(registrar.call_args.args[1], "Não me estresso com reunião.")
        self.assertEqual(self.send.call_args.args[3], "Anotado — entra na próxima leitura de domingo.")
        self.assertNotIn("pending_perfil_ajuste", session)
        self.persist.assert_called_once()

    def test_marcador_expirado_segue_fluxo_normal(self):
        velho = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        session = {"pending_perfil_ajuste": velho}
        with mock.patch("personal_diary.registrar_ajuste_personalidade") as registrar:
            tratada = self._responder("qual a minha agenda?", session)
        self.assertFalse(tratada)
        registrar.assert_not_called()
        self.assertNotIn("pending_perfil_ajuste", session)

    def test_comando_nao_e_consumido(self):
        session = {"pending_perfil_ajuste": datetime.now(timezone.utc).isoformat()}
        with mock.patch("personal_diary.registrar_ajuste_personalidade") as registrar, \
                mock.patch.object(tmd, "_handle_command", return_value="Ajuda") as comando:
            self.assertTrue(self._responder("/ajuda", session))
        comando.assert_called_once()
        registrar.assert_not_called()
        self.assertIn("pending_perfil_ajuste", session)

    def test_falha_ao_gravar_avisa(self):
        session = {"pending_perfil_ajuste": True}
        with mock.patch("personal_diary.registrar_ajuste_personalidade", side_effect=RuntimeError("x")):
            self.assertTrue(self._responder("texto", session))
        self.assertIn("Não consegui anotar", self.send.call_args.args[3])

    def test_validade_do_marcador(self):
        agora = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
        self.assertTrue(tmd._perfil_ajuste_ainda_valido("2026-09-27T01:00:00+00:00", agora))
        self.assertFalse(tmd._perfil_ajuste_ainda_valido("2026-09-25T01:00:00+00:00", agora))
        self.assertTrue(tmd._perfil_ajuste_ainda_valido(True, agora))


# --------------------------------------------------------------------------- #
# obter_estado_atual -> perfil_pessoal                                         #
# --------------------------------------------------------------------------- #

class PerfilPessoalEstadoAtualTest(unittest.TestCase):
    def _estado(self, perfil):
        from tools import hermes_tools
        from tools.tool_context import ToolContext
        with patch("morning_summary.build_morning_summary", return_value={"acoes": [], "perfil": perfil}):
            return hermes_tools.obter_estado_atual(ToolContext(_db=MagicMock()), {})

    def test_perfil_compacto_e_rotulado(self):
        perfil = {
            "resumo": "Pessoa metódica.",
            "estilo_comunicacao": "Direto, frases curtas.",
            "gatilhos": ["a", "b", "c", "d", "e", "f"],
            "energia": ["x" * 300],
            "rotinas": [],
            "atualizado_em": "2026-09-21T01:00:00+00:00",
        }
        res = self._estado(perfil)
        self.assertNotIn("perfil", res)
        pp = res["perfil_pessoal"]
        self.assertEqual(pp["resumo_narrativo"], "Pessoa metódica.")
        self.assertEqual(pp["estilo_comunicacao"], "Direto, frases curtas.")
        self.assertEqual(pp["gatilhos_de_estresse"], ["a", "b", "c", "d"])
        self.assertLessEqual(len(pp["fontes_de_energia"][0]), 121)
        self.assertEqual(pp["rotinas"], [])
        self.assertEqual(pp["atualizado_em"], "2026-09-21T01:00:00+00:00")
        self.assertIn("impressões semanais", pp["natureza"])
        self.assertIn("não fatos", pp["natureza"])

    def test_sem_perfil_nao_inclui_campo(self):
        res = self._estado(None)
        self.assertNotIn("perfil_pessoal", res)
        self.assertNotIn("perfil", res)

    def test_perfil_vazio_nao_inclui_campo(self):
        res = self._estado({"resumo": "", "gatilhos": [], "energia": [], "rotinas": []})
        self.assertNotIn("perfil_pessoal", res)

    def test_coletar_perfil_le_estilo_e_data_no_mesmo_doc(self):
        import morning_summary
        db = _Db({"usuarios/u1": {"ai_profile": {
            "personalidade": dict(PERFIL_ANTIGO, estilo_comunicacao="Direto"),
            "personalidade_atualizada_em": "2026-09-21T01:00:00+00:00",
        }}})
        with patch.dict(os.environ, {"HERMES_DEFAULT_USER_ID": "u1"}):
            perfil = morning_summary._coletar_perfil(db)
        self.assertEqual(perfil["estilo_comunicacao"], "Direto")
        self.assertEqual(perfil["atualizado_em"], "2026-09-21T01:00:00+00:00")
        self.assertEqual(perfil["gatilhos"], PERFIL_ANTIGO["gatilhos_de_estresse"])

    def test_instrucoes_do_mcp_citam_perfil_pessoal(self):
        import mcp_server
        self.assertIn("perfil_pessoal", mcp_server._INSTRUCTIONS)
        self.assertIn("diagnostico", mcp_server._INSTRUCTIONS)


if __name__ == "__main__":
    unittest.main()
