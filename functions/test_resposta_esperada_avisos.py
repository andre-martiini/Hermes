"""Sinal de resposta esperada, nível 2 (resposta_esperada_avisos): classificação pelo
Gemini flash, aviso no Telegram, janela de 4 h e os botões."""

import datetime as dt
import unittest
from unittest import mock

import resposta_esperada as re_
import resposta_esperada_avisos as av
import telegram_callbacks_resposta as tcr
from test_objetivos_whatsapp import _Db

UTC = dt.timezone.utc
AGORA = dt.datetime(2026, 10, 16, 14, 0, tzinfo=UTC)
CHAT = "5527999990000@c.us"
ENTRADA = {"acao_id": "acao-1", "etapa_id": "e1", "acao_titulo": "Documentação da GECC",
           "etapa_texto": "Aguardar a Maria confirmar o recebimento dos documentos",
           "aguardando_de": "Maria de Fátima", "nomes": [], "chat_ids": [CHAT], "grupos": []}


def _resultado(confianca="alta"):
    return {"considerada": True, "chat_id": CHAT, "grupo": False,
            "matches": [{"acao_id": "acao-1", "etapa_id": "e1", "aguardando_de": "Maria de Fátima",
                         "origem": "chat_vinculado", "confianca": confianca}]}


class _Base(unittest.TestCase):
    def setUp(self):
        self.db = _Db()
        self.avisos = []
        p = mock.patch("objetivos_whatsapp.objetivo_ativo_do_chat", return_value=None)
        p.start()
        self.addCleanup(mock.patch.stopall)

    def _msg(self, texto="Documentos recebidos com sucesso!", mid="m1", minutos=0, **extra):
        msg = {"id": mid, "chat_id": CHAT, "chat_name": "Maria de Fátima", "from_me": False, "content": texto,
               "message_type": "chat", "timestamp": AGORA + dt.timedelta(minutes=minutos), **extra}
        self.db.collection("whatsapp_messages").document(mid).set(msg)
        return msg

    def _avaliar(self, msg, classe="R", confianca="alta", agora=AGORA):
        self.contextos = getattr(self, "contextos", [])

        def classificar(db, contexto):
            self.contextos.append(contexto)
            return classe

        return av.avaliar(self.db, msg, _resultado(confianca), [ENTRADA], classificar=classificar,
                          avisar=lambda db, aid, aviso, texto: self.avisos.append((aid, aviso, texto)), agora=agora)


class TestAvaliar(_Base):
    def test_resposta_que_resolve_avisa_e_registra(self):
        res = self._avaliar(self._msg())
        self.assertEqual(res["status"], "avisado")
        aid, aviso, texto = self.avisos[0]
        self.assertEqual((aviso["classe"], aviso["acao_id"], aviso["etapa_id"]), ("R", "acao-1", "e1"))
        self.assertEqual(texto, "Documentos recebidos com sucesso!")
        self.assertIn(aid, self.db.collection(av.COLECAO_AVISOS).docs)
        self.assertEqual(self.db.collection("sinais_resposta_sombra").docs["m1"]["classificacao"]["classe"], "R")

    def test_ruido_nao_avisa_mas_fica_registrado(self):
        res = self._avaliar(self._msg("Bom dia!"), classe="N")
        self.assertEqual(res["status"], "ruido")
        self.assertEqual(self.avisos, [])
        self.assertEqual(self.db.collection("sinais_resposta_sombra").docs["m1"]["classificacao"]["classe"], "N")

    def test_confianca_baixa_e_conversa_com_objetivo_ficam_de_fora(self):
        self.assertIsNone(self._avaliar(self._msg(), confianca="baixa"))
        with mock.patch("objetivos_whatsapp.objetivo_ativo_do_chat", return_value={"id": "o1"}):
            self.assertEqual(self._avaliar(self._msg())["status"], "objetivo_ativo")
        self.assertEqual(self.avisos, [])

    def test_contexto_tem_a_etapa_quem_se_espera_e_a_minha_ultima_mensagem(self):
        self.db.collection("whatsapp_messages").document("antes").set({
            "chat_id": CHAT, "from_me": True, "content": "Maria, mandei os documentos por e-mail.",
            "timestamp": AGORA - dt.timedelta(hours=1)})
        self._avaliar(self._msg())
        contexto = self.contextos[0]
        for trecho in ("Documentação da GECC", "Aguardar a Maria confirmar", "Maria de Fátima",
                       "mandei os documentos por e-mail", "Documentos recebidos com sucesso!"):
            with self.subTest(trecho=trecho):
                self.assertIn(trecho, contexto)

    def test_audio_sem_transcricao_e_transcrito(self):
        with mock.patch("objetivos_whatsapp.transcrever_audio", return_value="recebi tudo, obrigada") as tr:
            self._avaliar(self._msg("", message_type="ptt"))
        tr.assert_called_once()
        self.assertIn("[ptt: recebi tudo, obrigada]", self.contextos[0])


class TestJanela(_Base):
    def test_depois_de_um_r_nao_classifica_de_novo_na_janela(self):
        self._avaliar(self._msg(mid="m1"))
        res = self._avaliar(self._msg("Obrigada!", mid="m2", minutos=30), agora=AGORA + dt.timedelta(minutes=30))
        self.assertEqual(res["status"], "janela")
        self.assertEqual(len(self.contextos), 1)
        self.assertEqual(len(self.avisos), 1)

    def test_depois_de_um_p_so_um_r_avisa_de_novo(self):
        self._avaliar(self._msg("Vou verificar e te falo", mid="m1"), classe="P")
        res = self._avaliar(self._msg("Ainda olhando", mid="m2", minutos=20), classe="P",
                            agora=AGORA + dt.timedelta(minutes=20))
        self.assertEqual(res["status"], "janela")
        res = self._avaliar(self._msg("Recebido, tudo certo", mid="m3", minutos=40), classe="R",
                            agora=AGORA + dt.timedelta(minutes=40))
        self.assertEqual(res["status"], "avisado")
        self.assertEqual([a[1]["classe"] for a in self.avisos], ["P", "R"])

    def test_passada_a_janela_avisa_de_novo(self):
        self._avaliar(self._msg(mid="m1"))
        depois = AGORA + av.JANELA_AVISO + dt.timedelta(minutes=1)
        res = self._avaliar(self._msg("Outra coisa", mid="m2"), classe="P", agora=depois)
        self.assertEqual(res["status"], "avisado")
        self.assertEqual(len(self.avisos), 2)


class TestBotoes(_Base):
    def _aviso(self):
        self._avaliar(self._msg())
        return self.avisos[0][0]

    def test_etapa_feita_marca_a_etapa_e_registra(self):
        aid = self._aviso()
        with mock.patch("tools.telegram_extended.editar_etapa_da_tarefa", return_value='OK|{"alteradas": {}}') as ed:
            texto = av.tratar_botao(self.db, aid, "feito")
        self.assertEqual(texto, "Etapa marcada como feita.")
        self.assertEqual(ed.call_args.args[1]["estado"], "feito")
        self.assertEqual(ed.call_args.args[1]["etapa_id"], "e1")
        self.assertEqual(self.db.collection(av.COLECAO_AVISOS).docs[aid]["avaliacao_dono"], "certo")

    def test_avaliacao_certo_errado_e_aviso_inexistente(self):
        aid = self._aviso()
        av.tratar_botao(self.db, aid, "nao")
        self.assertEqual(self.db.collection(av.COLECAO_AVISOS).docs[aid]["avaliacao_dono"], "errado")
        av.tratar_botao(self.db, aid, "ok")
        self.assertEqual(self.db.collection(av.COLECAO_AVISOS).docs[aid]["avaliacao_dono"], "certo")
        self.assertEqual(av.tratar_botao(self.db, "nao-existe", "ok"), "Aviso não encontrado.")

    def test_handler_do_telegram(self):
        with mock.patch.object(tcr, "_answer_callback_query") as responde, \
             mock.patch("resposta_esperada_avisos.tratar_botao", return_value="Anotado, obrigado.") as tb:
            self.assertTrue(tcr.handle(self.db, "tok", "q", "1", "respesp:a1:ok", {}, {}, None, mock.Mock(), None, None))
            self.assertFalse(tcr.handle(self.db, "tok", "q", "1", "outbox:x:ok", {}, {}, None, mock.Mock(), None, None))
        tb.assert_called_once_with(self.db, "a1", "ok")
        responde.assert_called_once()


class TestClassificador(unittest.TestCase):
    def _classificar(self, texto_modelo, chave="k"):
        keys = mock.Mock(exists=True, to_dict=lambda: {"gemini_api_key": chave} if chave else {})
        resposta = mock.Mock(text=texto_modelo)
        with mock.patch("main._cached_doc_get", return_value=keys), \
             mock.patch("gemini_cost_controls.generate_content_logged", return_value=resposta) as gen, \
             mock.patch("google.genai.Client"):
            classe = av.classificar_com_gemini(mock.Mock(), "contexto")
        return classe, gen

    def test_usa_o_gemini_flash_com_resposta_fechada(self):
        from gemini_cost_controls import GEMINI_AGENT_MODEL

        classe, gen = self._classificar("R")
        self.assertEqual(classe, "R")
        self.assertEqual(gen.call_args.kwargs["model"], GEMINI_AGENT_MODEL)
        self.assertEqual(gen.call_args.kwargs["config"].response_schema["enum"], ["R", "P", "N"])

    def test_resposta_invalida_ou_sem_chave_nao_classifica(self):
        self.assertIsNone(self._classificar("talvez")[0])
        self.assertIsNone(self._classificar("R", chave=None)[0])


class TestLigacaoNoSinal(unittest.TestCase):
    def setUp(self):
        re_._limpar_cache()
        self.addCleanup(re_._limpar_cache)

    def _processar(self, cfg):
        db = _Db()
        msg = {"id": "m1", "chat_id": CHAT, "chat_name": "Maria de Fátima", "from_me": False,
               "content": "Recebido!", "timestamp": AGORA}
        with mock.patch.object(re_, "_config", return_value=cfg), \
             mock.patch.object(re_, "_ler_indice", return_value=[{**ENTRADA, "desde": "2026-10-01T00:00:00+00:00"}]), \
             mock.patch("resposta_esperada_avisos.avaliar", return_value={"status": "avisado"}) as avaliar:
            res = re_.processar_mensagem(db, msg, AGORA)
        return res, avaliar

    def test_com_avisar_ligado_passa_pelo_nivel_2(self):
        res, avaliar = self._processar({"enabled": True, "avisar": True})
        avaliar.assert_called_once()
        self.assertEqual(res["nivel2"], {"status": "avisado"})

    def test_sem_avisar_fica_so_no_modo_sombra(self):
        _, avaliar = self._processar({"enabled": True})
        avaliar.assert_not_called()

    def test_indice_guarda_o_texto_da_etapa(self):
        tarefa = {"id": "t1", "titulo": "Ação", "status": "em andamento",
                  "plano_acao": [{"id": "e1", "text": "Aguardar o envio do CNPJ", "estado": "aguardando_terceiro",
                                  "aguardando_de": "Mariane Campos"}]}
        entradas, _ = re_.construir_indice([tarefa], [], AGORA)
        self.assertEqual(entradas[0]["etapa_texto"], "Aguardar o envio do CNPJ")


if __name__ == "__main__":
    unittest.main()
