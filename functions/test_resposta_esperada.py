"""Testes do sinal de resposta esperada, nivel 1, modo sombra (functions/resposta_esperada.py)."""

import json
import sys
import types
import unittest
from datetime import datetime, timezone
from unittest import mock

import resposta_esperada as re_

AGORA = datetime(2026, 9, 21, 15, 0, tzinfo=timezone.utc)
ANTES = "2026-09-21T10:00:00+00:00"
SEGREDO = "TEXTO-PRIVADO-DA-MENSAGEM-QUE-NUNCA-PODE-SER-GRAVADO"


class _Snap:
    def __init__(self, doc_id, dados):
        self.id = doc_id
        self._dados = dados
        self.exists = dados is not None

    def to_dict(self):
        return dict(self._dados) if self._dados is not None else {}


class _Doc:
    def __init__(self, db, colecao, doc_id):
        self.db, self.colecao, self.id = db, colecao, doc_id

    def get(self):
        self.db.leituras.append((self.colecao, self.id))
        return _Snap(self.id, self.db.dados.get((self.colecao, self.id)))

    def set(self, dados, merge=False):
        self.db.escritas.append((self.colecao, self.id, dados, merge))
        self.db.dados[(self.colecao, self.id)] = dados


class _Colecao:
    def __init__(self, db, nome):
        self.db, self.nome = db, nome

    def document(self, doc_id):
        return _Doc(self.db, self.nome, doc_id)


class _DB:
    def __init__(self, habilitado=True, entradas=None):
        self.dados, self.escritas, self.leituras = {}, [], []
        if habilitado is not None:
            self.dados[("system", "settings")] = {"atencao": {"resposta_esperada": {"enabled": habilitado}}}
        if entradas is not None:
            self.dados[("system", re_.INDICE_DOC)] = {"entradas": entradas}

    def collection(self, nome):
        return _Colecao(self, nome)

    def escritas_em(self, colecao):
        return [e for e in self.escritas if e[0] == colecao]


def _entrada(nomes=None, chat_ids=None, grupos=None, desde=ANTES, de="Marcos Marinho (TJES)", etapa="e1", acao="a1"):
    return {
        "acao_id": acao, "acao_titulo": "Acao", "etapa_id": etapa, "aguardando_de": de,
        "nomes": nomes if nomes is not None else re_.extrair_nomes(de),
        "chat_ids": chat_ids or [], "grupos": grupos or [], "desde": desde,
    }


def _msg(**campos):
    base = {
        "id": "chat_m1", "chat_id": "111@lid", "is_group": False, "from_me": False,
        "contact_name": "Marcos Marinho", "message_type": "chat", "content": SEGREDO,
        "timestamp": datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
    }
    base.update(campos)
    return base


def _tarefa(tid, etapas, status="em andamento", vinculos=None, titulo="Acao"):
    return {"id": tid, "status": status, "titulo": titulo, "plano_acao": etapas, "whatsapp_vinculos": vinculos or []}


def _etapa(eid, estado="aguardando_terceiro", de="Marcos Marinho (TJES)"):
    return {"id": eid, "text": "x", "estado": estado, "aguardando_de": de}


class TestExtrairNomes(unittest.TestCase):
    def _tokens(self, texto):
        return [n["tokens"] for n in re_.extrair_nomes(texto)]

    def test_nome_completo_com_orgao_entre_parenteses(self):
        nomes = re_.extrair_nomes("Marcos Marinho (TJES)")
        self.assertEqual([n["tokens"] for n in nomes], [["marcos", "marinho"]])
        self.assertFalse(nomes[0]["ambiguo"])

    def test_varios_nomes_e_primeiro_nome_e_ambiguo(self):
        nomes = re_.extrair_nomes("Gabriela Correa / Fernanda")
        self.assertEqual([n["tokens"] for n in nomes], [["gabriela", "correa"], ["fernanda"]])
        self.assertEqual([n["ambiguo"] for n in nomes], [False, True])

    def test_sigla_de_orgao_e_palavra_institucional_nao_viram_nome(self):
        self.assertEqual(self._tokens("Kamilla Scarpini/PROAD (planilha com junho)"), [["kamilla", "scarpini"]])
        self.assertEqual(self._tokens("CGU/RH do Ifes (protocolo SeCI)"), [])
        self.assertEqual(self._tokens("Ana Lima/STIC"), [["ana", "lima"]])
        self.assertEqual(self._tokens("Lucila Petrucia e analistas técnicos do SIGEX"), [["lucila", "petrucia"]])

    def test_nome_entre_parenteses_so_quando_parece_pessoa(self):
        self.assertIn(["wagner", "freitas"], self._tokens("Vetor Editora (Wagner Freitas)"))
        self.assertNotIn(["cristiano", "ferias"], self._tokens("Kamilla Scarpini (Cristiano de férias)"))

    def test_descricao_depois_do_travessao_e_ignorada(self):
        self.assertEqual(self._tokens("pai (Eugênio) — indicação de eletricista"), [["pai"]])

    def test_acentos_e_caixa_sao_normalizados(self):
        self.assertEqual(self._tokens("CLÁUDIA Rodrigues"), [["claudia", "rodrigues"]])

    def test_vazio(self):
        self.assertEqual(re_.extrair_nomes(""), [])
        self.assertEqual(re_.extrair_nomes(None), [])


class TestEsperaDoDonoOuIA(unittest.TestCase):
    def test_dono_ou_ia(self):
        for texto in (
            "André (aprovar os 2 rascunhos de WhatsApp no Telegram)",
            "André Araújo Martini (retomar terça 15/09)",
            "André (aprovar o envio no Telegram) e depois a equipe sênior do SIGEX",
            "Desenvolvedor (IA ligada ao sistema agenda-rei)",
            "Claude (revisar o diff)",
        ):
            with self.subTest(texto=texto):
                self.assertTrue(re_.e_espera_do_dono_ou_ia(texto))

    def test_terceiros_nao_sao_dono(self):
        for texto in ("André Silva (fornecedor)", "Marcos Marinho (TJES)", "Gabriela e André", "", None):
            with self.subTest(texto=texto):
                self.assertFalse(re_.e_espera_do_dono_ou_ia(texto))


class TestConstruirIndice(unittest.TestCase):
    def test_so_etapas_aguardando_de_acoes_ativas(self):
        tarefas = [
            _tarefa("a1", [_etapa("e1"), _etapa("e2", estado="pendente"), _etapa("e3", estado="feito")]),
            _tarefa("a2", [_etapa("e4")], status="stand-by"),
            _tarefa("a3", [_etapa("e5")], status="concluído"),
        ]
        entradas, dono = re_.construir_indice(tarefas, [], AGORA)
        self.assertEqual([(e["acao_id"], e["etapa_id"]) for e in entradas], [("a1", "e1"), ("a2", "e4")])
        self.assertEqual(dono, 0)

    def test_esperas_do_dono_ou_ia_ficam_de_fora_e_sao_contadas(self):
        tarefas = [_tarefa("a1", [_etapa("e1", de="André (aprovar no Telegram)"), _etapa("e2")])]
        entradas, dono = re_.construir_indice(tarefas, [], AGORA)
        self.assertEqual([e["etapa_id"] for e in entradas], ["e2"])
        self.assertEqual(dono, 1)

    def test_vinculos_da_acao_viram_chat_ids_e_grupos(self):
        vinculos = [
            {"chat_id": "g1@g.us", "is_group": True, "chat_name": "Grupo"},
            {"chat_id": "p1@lid", "is_group": False, "chat_name": "Pessoa"},
            {"chat_id": "", "is_group": False},
        ]
        entradas, _ = re_.construir_indice([_tarefa("a1", [_etapa("e1")], vinculos=vinculos)], [], AGORA)
        self.assertEqual(entradas[0]["chat_ids"], ["g1@g.us", "p1@lid"])
        self.assertEqual(entradas[0]["grupos"], ["g1@g.us"])

    def test_desde_e_preservado_enquanto_a_espera_e_a_mesma(self):
        tarefas = [_tarefa("a1", [_etapa("e1")])]
        primeira, _ = re_.construir_indice(tarefas, [], AGORA)
        depois = datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc)
        segunda, _ = re_.construir_indice(tarefas, primeira, depois)
        self.assertEqual(segunda[0]["desde"], AGORA.isoformat())

    def test_desde_reinicia_quando_muda_de_quem_se_espera(self):
        primeira, _ = re_.construir_indice([_tarefa("a1", [_etapa("e1", de="Fulano Silva")])], [], AGORA)
        depois = datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc)
        segunda, _ = re_.construir_indice([_tarefa("a1", [_etapa("e1", de="Beltrano Souza")])], primeira, depois)
        self.assertEqual(segunda[0]["desde"], depois.isoformat())

    def test_espera_sem_nome_mantem_os_chats_ligados(self):
        vinculos = [{"chat_id": "p1@lid", "is_group": False}]
        entradas, _ = re_.construir_indice([_tarefa("a1", [_etapa("e1", de="")], vinculos=vinculos)], [], AGORA)
        self.assertEqual(entradas[0]["nomes"], [])
        self.assertEqual(entradas[0]["chat_ids"], ["p1@lid"])


class TestCasarMensagem(unittest.TestCase):
    def _unico(self, resultado):
        self.assertEqual(len(resultado["matches"]), 1, resultado)
        return resultado["matches"][0]

    def test_chat_individual_vinculado_com_nome_e_alta(self):
        r = re_.casar_mensagem(_msg(), [_entrada(chat_ids=["111@lid"])])
        m = self._unico(r)
        self.assertEqual((m["origem"], m["confianca"]), ("chat_vinculado", "alta"))

    def test_chat_individual_vinculado_sem_o_nome_e_media(self):
        r = re_.casar_mensagem(_msg(contact_name="Outra Pessoa"), [_entrada(chat_ids=["111@lid"])])
        m = self._unico(r)
        self.assertEqual((m["origem"], m["confianca"]), ("chat_vinculado_sem_nome", "media"))

    def test_chat_vinculado_e_espera_sem_nomes_e_alta(self):
        r = re_.casar_mensagem(_msg(contact_name="Qualquer"), [_entrada(nomes=[], de="", chat_ids=["111@lid"])])
        self.assertEqual(self._unico(r)["confianca"], "alta")

    def test_nome_completo_sem_vinculo_e_media(self):
        m = self._unico(re_.casar_mensagem(_msg(), [_entrada()]))
        self.assertEqual((m["origem"], m["confianca"]), ("nome_do_contato", "media"))

    def test_so_o_primeiro_nome_sem_vinculo_e_baixa(self):
        entrada = _entrada(de="Fernanda")
        m = self._unico(re_.casar_mensagem(_msg(contact_name="Fernanda Nogueira"), [entrada]))
        self.assertEqual(m["confianca"], "baixa")

    def test_nome_parcial_de_dois_nomes_nao_casa(self):
        r = re_.casar_mensagem(_msg(contact_name="Marcos Silva"), [_entrada()])
        self.assertEqual(r["matches"], [])

    def test_remetente_sem_relacao_nao_casa(self):
        r = re_.casar_mensagem(_msg(contact_name="Joao Pereira"), [_entrada()])
        self.assertTrue(r["considerada"])
        self.assertEqual(r["matches"], [])

    def test_acentos_e_caixa_nao_atrapalham(self):
        entrada = _entrada(de="Márcio Vilatec")
        self._unico(re_.casar_mensagem(_msg(contact_name="MARCIO VILATEC Elétrica"), [entrada]))

    def test_grupo_vinculado_com_o_autor_certo_e_alta(self):
        entrada = _entrada(chat_ids=["g1@g.us"], grupos=["g1@g.us"])
        msg = _msg(chat_id="g1@g.us", is_group=True, author_name="Marcos Marinho", contact_name="Grupo")
        m = self._unico(re_.casar_mensagem(msg, [entrada]))
        self.assertEqual((m["origem"], m["confianca"]), ("grupo_vinculado_autor", "alta"))

    def test_grupo_vinculado_com_autor_de_primeiro_nome_e_media(self):
        entrada = _entrada(de="Gabriela", chat_ids=["g1@g.us"], grupos=["g1@g.us"])
        msg = _msg(chat_id="g1@g.us", is_group=True, author_name="Gabriela Correa")
        self.assertEqual(self._unico(re_.casar_mensagem(msg, [entrada]))["confianca"], "media")

    def test_grupo_vinculado_com_outro_autor_e_suprimido(self):
        entrada = _entrada(chat_ids=["g1@g.us"], grupos=["g1@g.us"])
        msg = _msg(chat_id="g1@g.us", is_group=True, author_name="Fulano Qualquer")
        r = re_.casar_mensagem(msg, [entrada])
        self.assertEqual(r["matches"], [])
        self.assertEqual(r["suprimidas_grupo_sem_autor"], 1)

    def test_autor_em_grupo_nao_vinculado_e_baixa(self):
        msg = _msg(chat_id="g9@g.us", is_group=True, author_name="Marcos Marinho")
        m = self._unico(re_.casar_mensagem(msg, [_entrada()]))
        self.assertEqual((m["origem"], m["confianca"]), ("autor_em_grupo_nao_vinculado", "baixa"))

    def test_mensagem_do_proprio_dono_e_ignorada(self):
        r = re_.casar_mensagem(_msg(from_me=True), [_entrada()])
        self.assertFalse(r["considerada"])
        self.assertEqual(r["matches"], [])

    def test_broadcast_e_newsletter_sao_ignorados(self):
        for chat in ("status@broadcast", "123@newsletter"):
            with self.subTest(chat=chat):
                self.assertFalse(re_.casar_mensagem(_msg(chat_id=chat), [_entrada()])["considerada"])

    def test_mensagem_anterior_ao_desde_nao_conta(self):
        entrada = _entrada(desde="2026-09-21T13:00:00+00:00")
        self.assertEqual(re_.casar_mensagem(_msg(), [entrada])["matches"], [])

    def test_timestamp_em_texto_e_lido(self):
        anterior = _msg(timestamp="2026-09-21T09:00:00Z")
        posterior = _msg(timestamp="2026-09-21T12:00:00Z")
        entrada = _entrada(desde="2026-09-21T10:00:00Z")
        self.assertEqual(re_.casar_mensagem(anterior, [entrada])["matches"], [])
        self.assertEqual(len(re_.casar_mensagem(posterior, [entrada])["matches"]), 1)

    def test_limite_de_casamentos_por_mensagem(self):
        entradas = [_entrada(etapa=f"e{i}") for i in range(15)]
        r = re_.casar_mensagem(_msg(), entradas)
        self.assertEqual(len(r["matches"]), re_.MAX_MATCHES_POR_MENSAGEM)
        self.assertEqual(r["truncados"], 5)

    def test_casamentos_saem_ordenados_por_confianca(self):
        alta = _entrada(etapa="alta", chat_ids=["111@lid"])
        baixa = _entrada(etapa="baixa", de="Marcos")
        r = re_.casar_mensagem(_msg(), [baixa, alta])
        self.assertEqual([m["etapa_id"] for m in r["matches"]], ["alta", "baixa"])


class TestProcessarMensagem(unittest.TestCase):
    def setUp(self):
        re_._limpar_cache()

    def test_desligado_nao_le_indice_nem_grava(self):
        db = _DB(habilitado=False, entradas=[_entrada()])
        self.assertIsNone(re_.processar_mensagem(db, _msg(), AGORA))
        self.assertEqual(db.escritas, [])
        self.assertNotIn(("system", re_.INDICE_DOC), db.leituras)

    def test_ligado_sem_indice_nao_grava(self):
        db = _DB(habilitado=True, entradas=[])
        self.assertIsNone(re_.processar_mensagem(db, _msg(), AGORA))
        self.assertEqual(db.escritas, [])

    def test_com_casamento_grava_so_ids_e_nunca_o_texto(self):
        db = _DB(entradas=[_entrada()])
        re_.processar_mensagem(db, _msg(), AGORA)
        (colecao, doc_id, dados, _), = db.escritas_em(re_.SOMBRA_COLLECTION)
        self.assertEqual(doc_id, "chat_m1")
        self.assertEqual(dados["modo"], "sombra")
        self.assertEqual(dados["matches"][0]["etapa_id"], "e1")
        self.assertNotIn(SEGREDO, json.dumps(dados, default=str))
        self.assertNotIn("content", dados)

    def test_contadores_do_dia_com_incremento(self):
        db = _DB(entradas=[_entrada(chat_ids=["111@lid"])])
        re_.processar_mensagem(db, _msg(), AGORA)
        (_, doc_id, dados, merge), = db.escritas_em(re_.CONTADORES_COLLECTION)
        self.assertEqual(doc_id, "2026-09-21")
        self.assertTrue(merge)
        self.assertEqual(dados["avaliadas"].value, 1)
        self.assertEqual(dados["com_match"].value, 1)
        self.assertEqual(dados["conf_alta"].value, 1)

    def test_considerada_sem_casamento_so_conta_avaliada(self):
        db = _DB(entradas=[_entrada()])
        re_.processar_mensagem(db, _msg(contact_name="Joao Pereira"), AGORA)
        self.assertEqual(db.escritas_em(re_.SOMBRA_COLLECTION), [])
        (_, _, dados, _), = db.escritas_em(re_.CONTADORES_COLLECTION)
        self.assertEqual(set(dados), {"avaliadas"})

    def test_suprimidas_de_grupo_entram_no_contador(self):
        entrada = _entrada(chat_ids=["g1@g.us"], grupos=["g1@g.us"])
        msg = _msg(chat_id="g1@g.us", is_group=True, author_name="Fulano Qualquer")
        db = _DB(entradas=[entrada])
        re_.processar_mensagem(db, msg, AGORA)
        (_, _, dados, _), = db.escritas_em(re_.CONTADORES_COLLECTION)
        self.assertEqual(dados["suprimidas_grupo_sem_autor"].value, 1)

    def test_mensagem_sem_id_conta_mas_nao_grava_documento(self):
        db = _DB(entradas=[_entrada()])
        re_.processar_mensagem(db, _msg(id=None, wa_message_id=None), AGORA)
        self.assertEqual(db.escritas_em(re_.SOMBRA_COLLECTION), [])
        self.assertEqual(len(db.escritas_em(re_.CONTADORES_COLLECTION)), 1)

    def test_mensagem_do_dono_nao_gera_nada(self):
        db = _DB(entradas=[_entrada()])
        self.assertIsNone(re_.processar_mensagem(db, _msg(from_me=True), AGORA))
        self.assertEqual(db.escritas, [])

    def test_estado_fica_em_cache(self):
        db = _DB(entradas=[_entrada()])
        re_.processar_mensagem(db, _msg(id="m1"), AGORA)
        re_.processar_mensagem(db, _msg(id="m2"), AGORA)
        self.assertEqual(db.leituras.count(("system", "settings")), 1)
        self.assertEqual(db.leituras.count(("system", re_.INDICE_DOC)), 1)


class TestReconstruirIndice(unittest.TestCase):
    class _SnapTarefa:
        def __init__(self, tid, dados):
            self.id, self._d = tid, dados

        def to_dict(self):
            return dict(self._d)

    def _snaps(self, *tarefas):
        return [self._SnapTarefa(t["id"], {k: v for k, v in t.items() if k != "id"}) for t in tarefas]

    def test_desligado_nao_grava(self):
        db = _DB(habilitado=False)
        r = re_.reconstruir_indice(db, self._snaps(_tarefa("a1", [_etapa("e1")])), AGORA)
        self.assertEqual(r, {"desligado": True, "gravado": False})
        self.assertEqual(db.escritas, [])

    def test_grava_o_indice_com_as_esperas(self):
        db = _DB()
        tarefas = self._snaps(_tarefa("a1", [_etapa("e1"), _etapa("e2", de="André (aprovar)")]))
        r = re_.reconstruir_indice(db, tarefas, AGORA)
        self.assertTrue(r["gravado"])
        self.assertEqual((r["esperas_terceiros"], r["esperas_dono_ou_ia"]), (1, 1))
        (_, doc_id, dados, _), = db.escritas_em("system")
        self.assertEqual(doc_id, re_.INDICE_DOC)
        self.assertEqual([e["etapa_id"] for e in dados["entradas"]], ["e1"])

    def test_nao_regrava_quando_nada_mudou(self):
        db = _DB()
        tarefas = self._snaps(_tarefa("a1", [_etapa("e1")]))
        re_.reconstruir_indice(db, tarefas, AGORA)
        depois = datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc)
        r = re_.reconstruir_indice(db, tarefas, depois)
        self.assertFalse(r["gravado"])
        self.assertEqual(len(db.escritas_em("system")), 1)
        self.assertEqual(db.dados[("system", re_.INDICE_DOC)]["entradas"][0]["desde"], AGORA.isoformat())

    def test_grava_de_novo_quando_a_espera_some(self):
        db = _DB()
        re_.reconstruir_indice(db, self._snaps(_tarefa("a1", [_etapa("e1")])), AGORA)
        r = re_.reconstruir_indice(db, self._snaps(_tarefa("a1", [_etapa("e1", estado="feito")])), AGORA)
        self.assertTrue(r["gravado"])
        self.assertEqual(db.dados[("system", re_.INDICE_DOC)]["entradas"], [])


class TestGatilho(unittest.TestCase):
    def _rodar(self, processar):
        import atencao_whatsapp

        snap = mock.Mock(exists=True, id="chat_m1")
        snap.to_dict.return_value = {"chat_id": "111@lid", "from_me": False}
        evento = mock.Mock(data=snap)
        fake_main = types.SimpleNamespace(get_db=lambda: "DB")
        with mock.patch.dict(sys.modules, {"main": fake_main}),                 mock.patch("secretario_whatsapp.processar_mensagem_secretario"),                 mock.patch.object(atencao_whatsapp, "_processar_promessa") as promessa,                 mock.patch.object(atencao_whatsapp, "_processar_audio") as audio,                 mock.patch.object(atencao_whatsapp, "_processar_aprovacao_outbox") as aprovacao,                 mock.patch.object(re_, "processar_mensagem", processar):
            atencao_whatsapp.on_whatsapp_message_atencao.__wrapped__(evento)
        return promessa, audio, aprovacao

    def test_gatilho_chama_o_sinal_com_o_banco_e_a_mensagem(self):
        chamado = mock.Mock()
        self._rodar(chamado)
        db, mensagem = chamado.call_args.args
        self.assertEqual(db, "DB")
        self.assertEqual(mensagem["chat_id"], "111@lid")

    def test_falha_no_sinal_nao_derruba_os_outros_detectores(self):
        promessa, audio, aprovacao = self._rodar(mock.Mock(side_effect=RuntimeError("boom")))
        promessa.assert_called_once()
        audio.assert_called_once()
        aprovacao.assert_called_once()


if __name__ == "__main__":
    unittest.main()
