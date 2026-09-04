"""Testes dos detectores reativos de WhatsApp (functions/atencao_whatsapp.py)."""

from datetime import datetime, timezone
import unittest
from unittest import mock

from atencao_whatsapp import (
    ESTADO_PROMESSA_ABERTA,
    ESTADO_PROMESSA_VENCIDA,
    TIPO_AUDIO_RELEVANTE,
    TIPO_PROMESSA_SEM_RETORNO,
    _obter_whatsapp_owner_chat_id,
    _processar_aprovacao_outbox,
    _processar_audio,
    avaliar_audio,
    avaliar_promessas_vencidas,
    decidir_acao_mensagem_from_me,
    interpretar_resposta_aprovacao_whatsapp,
    mensagem_cumpre_promessa,
    mensagem_e_promessa,
    mesclar_ou_criar_item_audio,
    montar_promessa,
)


class TestPromessaSemRetorno(unittest.TestCase):
    def test_cada_padrao_casa(self):
        frases = [
            "Vou ver e te retorno",
            "Já estou vendo",
            "Te aviso ainda hoje",
            "Vou verificar e te falo",
            "Deixa comigo",
            "Pode deixar",
        ]
        for frase in frases:
            with self.subTest(frase=frase):
                self.assertTrue(mensagem_e_promessa(frase), f"deveria casar: {frase}")

    def test_frase_parecida_sem_compromisso_nao_casa(self):
        self.assertFalse(mensagem_e_promessa("estou vendo o jogo"))

    def test_mensagem_curta_nao_cumpre(self):
        self.assertFalse(mensagem_cumpre_promessa("ok", tem_midia=False))
        self.assertFalse(mensagem_cumpre_promessa("beleza", tem_midia=False))

    def test_mensagem_longa_cumpre(self):
        texto = "Já resolvi o problema que você tinha me mandado, ficou tudo certo agora."
        self.assertGreater(len(texto), 40)
        self.assertTrue(mensagem_cumpre_promessa(texto, tem_midia=False))

    def test_midia_sempre_cumpre_mesmo_curta(self):
        self.assertTrue(mensagem_cumpre_promessa("oi", tem_midia=True))

    def test_mensagem_que_e_nova_promessa_nao_cumpre_a_anterior(self):
        # Uma promessa nova substitui, nao cumpre - mesmo sendo "longa" o suficiente.
        self.assertFalse(mensagem_cumpre_promessa("Vou verificar e te aviso ainda hoje sem falta", tem_midia=False))

    def test_promessa_nova_substitui_antiga(self):
        horas = 4
        mensagem_antiga = {
            "chat_id": "chat-1", "chat_name": "Guilherme", "wa_message_id": "m1",
            "content": "Deixa comigo", "message_type": "chat",
            "timestamp": datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc),
        }
        promessa_antiga = montar_promessa(mensagem_antiga, horas)

        mensagem_nova = {
            "chat_id": "chat-1", "chat_name": "Guilherme", "wa_message_id": "m2",
            "content": "Pode deixar", "message_type": "chat",
            "timestamp": datetime(2026, 9, 3, 11, 0, tzinfo=timezone.utc),
        }
        decisao = decidir_acao_mensagem_from_me(mensagem_nova, promessa_antiga, horas)

        self.assertEqual(decisao["acao"], "criar")
        self.assertTrue(decisao["substituiu"])
        self.assertEqual(decisao["promessa"]["mensagem_id"], "m2")

    def test_vencimento_gera_item_com_chave_dedupe_esperada(self):
        promessa = {
            "chat_id": "chat-2", "chat_name": "Fulano", "mensagem_id": "m5",
            "texto": "Te retorno ainda hoje",
            "prometido_em": datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc),
            "vence_em": datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc),
            "estado": ESTADO_PROMESSA_ABERTA,
            "acao_id": None,
        }
        agora = datetime(2026, 9, 3, 13, 0, tzinfo=timezone.utc)
        itens = avaliar_promessas_vencidas([promessa], agora)
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertEqual(item["chave_dedupe"], "promessa_sem_retorno:chat-2:m5")
        self.assertEqual(item["tipo"], TIPO_PROMESSA_SEM_RETORNO)
        self.assertEqual(item["origem"], "whatsapp")
        self.assertIn("Fulano", item["titulo"])

    def test_promessa_nao_vencida_nao_gera_item(self):
        promessa = {
            "chat_id": "chat-3", "chat_name": "Ciclano", "mensagem_id": "m6",
            "texto": "Já estou vendo",
            "prometido_em": datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc),
            "vence_em": datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc),
            "estado": ESTADO_PROMESSA_ABERTA,
        }
        agora = datetime(2026, 9, 3, 11, 0, tzinfo=timezone.utc)
        itens = avaliar_promessas_vencidas([promessa], agora)
        self.assertEqual(len(itens), 0)

    def test_resposta_depois_do_vencimento_resolve_o_item(self):
        promessa_vencida = {
            "chat_id": "chat-2", "chat_name": "Fulano", "mensagem_id": "m5",
            "texto": "Te retorno ainda hoje",
            "estado": ESTADO_PROMESSA_VENCIDA,
        }
        mensagem_resposta = {
            "chat_id": "chat-2", "wa_message_id": "m9", "message_type": "chat",
            "content": "Consegui resolver, ficou tudo certo com o fornecedor agora.",
            "timestamp": datetime(2026, 9, 3, 15, 30, tzinfo=timezone.utc),
        }
        decisao = decidir_acao_mensagem_from_me(mensagem_resposta, promessa_vencida, horas=4)
        self.assertEqual(decisao["acao"], "cumprir")
        self.assertIn("resolver_item_fila", decisao)
        resolver = decisao["resolver_item_fila"]
        self.assertEqual(resolver["chave_dedupe"], "promessa_sem_retorno:chat-2:m5")
        self.assertEqual(resolver["desfecho"], "respondeu em 15:30")


class TestAudioRelevante(unittest.TestCase):
    def _mensagem_audio(self, **overrides):
        base = {
            "from_me": False,
            "message_type": "ptt",
            "chat_id": "chat-audio-1",
            "chat_name": "Serviço Social Piúma",
            "wa_message_id": "a1",
            "author_name": "Maria",
            "media": {},
            "timestamp": datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc),
        }
        base.update(overrides)
        return base

    def test_audio_de_chat_vinculado_gera_item(self):
        contexto = {"chat_vinculado": True, "acao": {"id": "acao-1", "titulo": "Processo X"}}
        item = avaliar_audio(self._mensagem_audio(), contexto)
        self.assertIsNotNone(item)
        self.assertEqual(item["tipo"], TIPO_AUDIO_RELEVANTE)
        self.assertEqual(item["chave_dedupe"], "audio_relevante:chat-audio-1:a1")
        self.assertIn("Processo X", item["titulo"])

    def test_audio_de_chat_nao_vinculado_nao_gera(self):
        contexto = {"chat_vinculado": False, "acao": None}
        item = avaliar_audio(self._mensagem_audio(), contexto)
        self.assertIsNone(item)

    def test_audio_from_me_nao_gera(self):
        contexto = {"chat_vinculado": True, "acao": {"id": "acao-1", "titulo": "Processo X"}}
        item = avaliar_audio(self._mensagem_audio(from_me=True), contexto)
        self.assertIsNone(item)

    def test_duracao_desconhecida_e_tratada_como_relevante(self):
        contexto = {"chat_vinculado": True, "acao": {"id": "acao-1", "titulo": "Processo X"}, "segundos_min": 20}
        item = avaliar_audio(self._mensagem_audio(media={}), contexto)
        self.assertIsNotNone(item)

    def test_duracao_curta_conhecida_nao_gera(self):
        contexto = {"chat_vinculado": True, "acao": {"id": "acao-1", "titulo": "Processo X"}, "segundos_min": 20}
        item = avaliar_audio(self._mensagem_audio(media={"duration_seconds": 5}), contexto)
        self.assertIsNone(item)

    def test_tres_audios_em_5_min_viram_um_item_com_tres_ids(self):
        contexto = {"chat_vinculado": True, "acao": {"id": "acao-1", "titulo": "Processo X"}}

        m1 = self._mensagem_audio(wa_message_id="a1", timestamp=datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc))
        item1 = avaliar_audio(m1, contexto)
        merged1 = mesclar_ou_criar_item_audio(None, item1, m1)
        self.assertEqual(merged1["evidencia"]["mensagem_ids"], ["a1"])

        m2 = self._mensagem_audio(wa_message_id="a2", timestamp=datetime(2026, 9, 3, 9, 2, tzinfo=timezone.utc))
        item2 = avaliar_audio(m2, contexto)
        merged2 = mesclar_ou_criar_item_audio(merged1, item2, m2)
        self.assertEqual(merged2["evidencia"]["mensagem_ids"], ["a1", "a2"])
        self.assertEqual(merged2["chave_dedupe"], "audio_relevante:chat-audio-1:a1")

        m3 = self._mensagem_audio(wa_message_id="a3", timestamp=datetime(2026, 9, 3, 9, 5, tzinfo=timezone.utc))
        item3 = avaliar_audio(m3, contexto)
        merged3 = mesclar_ou_criar_item_audio(merged2, item3, m3)
        self.assertEqual(merged3["evidencia"]["mensagem_ids"], ["a1", "a2", "a3"])
        self.assertEqual(merged3["chave_dedupe"], "audio_relevante:chat-audio-1:a1")

    def test_audio_fora_da_janela_vira_item_novo(self):
        contexto = {"chat_vinculado": True, "acao": {"id": "acao-1", "titulo": "Processo X"}}
        m1 = self._mensagem_audio(wa_message_id="a1", timestamp=datetime(2026, 9, 3, 9, 0, tzinfo=timezone.utc))
        item1 = avaliar_audio(m1, contexto)
        merged1 = mesclar_ou_criar_item_audio(None, item1, m1)

        m2 = self._mensagem_audio(wa_message_id="a2", timestamp=datetime(2026, 9, 3, 9, 30, tzinfo=timezone.utc))
        item2 = avaliar_audio(m2, contexto)
        merged2 = mesclar_ou_criar_item_audio(merged1, item2, m2)
        # Fora da janela de 10 min -> novo item, nao mesclado.
        self.assertEqual(merged2["chave_dedupe"], "audio_relevante:chat-audio-1:a2")
        self.assertEqual(merged2["evidencia"]["mensagem_ids"], ["a2"])

    def test_prioridade_alta_para_acao_critica(self):
        contexto = {
            "chat_vinculado": True,
            "acao": {"id": "acao-1", "titulo": "Processo Critico", "degradation_count": 3},
        }
        item = avaliar_audio(self._mensagem_audio(), contexto)
        self.assertEqual(item["prioridade"], "alta")


class _MockDocSnap:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = dict(data) if data is not None else None
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else {}


class _MockDocRef:
    def __init__(self, col, doc_id: str):
        self.col = col
        self.id = doc_id

    def get(self):
        data = self.col._docs.get(self.id)
        return _MockDocSnap(self.id, data)

    def set(self, data, merge=False):
        if merge and self.id in self.col._docs:
            self.col._docs[self.id].update(data)
        else:
            self.col._docs[self.id] = dict(data)

    def update(self, data):
        if self.id not in self.col._docs:
            raise KeyError(f"Doc {self.id} does not exist")
        self.col._docs[self.id].update(data)


def _get_nested(d, path):
    curr = d
    for p in path.split("."):
        if not isinstance(curr, dict):
            return None
        curr = curr.get(p)
    return curr


class _MockQuery:
    def __init__(self, col, items):
        self.col = col
        self.items = items

    def where(self, field, op, val):
        filtered = [
            (k, v) for k, v in self.items
            if op == "==" and _get_nested(v, field) == val
        ]
        return _MockQuery(self.col, filtered)

    def stream(self):
        return [_MockDocSnap(k, v) for k, v in self.items]


class _MockCollection:
    def __init__(self, db, name: str):
        self.db = db
        self.name = name
        self._docs: dict[str, dict] = {}

    def document(self, doc_id: str):
        return _MockDocRef(self, doc_id)

    def where(self, field, op, val):
        filtered = [
            (k, v) for k, v in self._docs.items()
            if op == "==" and _get_nested(v, field) == val
        ]
        return _MockQuery(self, filtered)

    def stream(self):
        return [_MockDocSnap(k, v) for k, v in self._docs.items()]


class _MockDB:
    def __init__(self):
        self._collections: dict[str, _MockCollection] = {}

    def collection(self, name: str) -> _MockCollection:
        if name not in self._collections:
            self._collections[name] = _MockCollection(self, name)
        return self._collections[name]


class TestHookAgentRequests(unittest.TestCase):
    @mock.patch("atencao_whatsapp._flag_audio", return_value=(True, 20))
    @mock.patch("atencao_whatsapp._acoes_ativas_por_chat_cached")
    def test_hook_cria_e_mescla_agent_request(self, mock_acoes, mock_flag):
        mock_acoes.return_value = {"chat-test": {"id": "acao-xyz", "titulo": "Ação Teste"}}
        db = _MockDB()

        # Primeiro áudio
        m1 = {
            "from_me": False,
            "message_type": "ptt",
            "chat_id": "chat-test",
            "chat_name": "Guilherme",
            "wa_message_id": "aud1",
            "author_name": "Guilherme",
            "media": {},
            "timestamp": datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc),
        }
        _processar_audio(db, m1)

        atencao_col = db.collection("atencao")
        req_col = db.collection("agent_requests")

        self.assertEqual(len(atencao_col._docs), 1)
        self.assertEqual(len(req_col._docs), 1)

        expected_atencao_id = "audio_relevante:chat-test:aud1"
        expected_req_id = f"consolidar_audio:{expected_atencao_id}"
        self.assertIn(expected_req_id, req_col._docs)

        req_doc = req_col._docs[expected_req_id]
        self.assertEqual(req_doc["status"], "pendente")
        self.assertEqual(req_doc["tipo"], "consolidar_audio")
        self.assertEqual(req_doc["item_atencao_id"], expected_atencao_id)
        self.assertEqual(req_doc["acao_id"], "acao-xyz")
        self.assertEqual(req_doc["payload"]["mensagem_ids"], ["aud1"])
        self.assertEqual(req_doc["payload"]["chat_id"], "chat-test")
        self.assertEqual(req_doc["payload"]["chat_name"], "Guilherme")

        # Segundo áudio 2 minutos depois (mesma janela de 10 min)
        m2 = {
            "from_me": False,
            "message_type": "ptt",
            "chat_id": "chat-test",
            "chat_name": "Guilherme",
            "wa_message_id": "aud2",
            "author_name": "Guilherme",
            "media": {},
            "timestamp": datetime(2026, 9, 3, 10, 2, tzinfo=timezone.utc),
        }
        _processar_audio(db, m2)

        # Não deve criar um novo doc, deve manter o mesmo atualizado
        self.assertEqual(len(req_col._docs), 1)
        req_doc2 = req_col._docs[expected_req_id]
        self.assertEqual(req_doc2["status"], "pendente")
        self.assertEqual(req_doc2["payload"]["mensagem_ids"], ["aud1", "aud2"])


class TestAprovacaoOutboxWhatsApp(unittest.TestCase):
    def setUp(self):
        self.owner_chat_id = "5511999999999@c.us"
        self.rascunho_unico = [{
            "id": "outbox-abc-123",
            "outbox_id": "outbox-abc-123",
            "content": "Texto do rascunho original para o cliente",
            "status": "aguardando_aprovacao",
        }]

    def test_aprovacao_variacoes_sim_ok_pode_manda(self):
        frases_aprovacao = [
            "sim", "SIM", "Sim.", "ok", "OK!", "pode", "manda", "mandar",
            "pode mandar", "pode enviar", "aprova", "aprovar", "envia",
            "confirma", "confirmar", "positivo", "vai", "manda bala", "manda ver",
        ]
        for frase in frases_aprovacao:
            with self.subTest(frase=frase):
                msg = {
                    "from_me": True,
                    "chat_id": self.owner_chat_id,
                    "content": frase,
                }
                res = interpretar_resposta_aprovacao_whatsapp(
                    msg, self.rascunho_unico, self.owner_chat_id
                )
                self.assertIsNotNone(res)
                self.assertEqual(res["acao"], "aprovar")
                self.assertEqual(res["outbox_id"], "outbox-abc-123")

    def test_descarte_variacoes_nao_descarta_cancela(self):
        frases_descarte = [
            "nao", "não", "NÃO!", "descarta", "descartar", "cancela",
            "cancelar", "ignora", "ignorar", "lixo", "deleta", "apaga",
            "descarta isso", "cancela isso",
        ]
        for frase in frases_descarte:
            with self.subTest(frase=frase):
                msg = {
                    "from_me": True,
                    "chat_id": self.owner_chat_id,
                    "content": frase,
                }
                res = interpretar_resposta_aprovacao_whatsapp(
                    msg, self.rascunho_unico, self.owner_chat_id
                )
                self.assertIsNotNone(res)
                self.assertEqual(res["acao"], "descartar")
                self.assertEqual(res["outbox_id"], "outbox-abc-123")

    def test_edicao_texto_livre(self):
        textos_edicao = [
            "Oi Dr. Marcos, por favor confirme a reunião para quinta às 15h.",
            "Não posso ir amanhã, prefiro na sexta às 10h.",
            "Altera o valor para R$ 150,00",
        ]
        for texto in textos_edicao:
            with self.subTest(texto=texto):
                msg = {
                    "from_me": True,
                    "chat_id": self.owner_chat_id,
                    "content": texto,
                }
                res = interpretar_resposta_aprovacao_whatsapp(
                    msg, self.rascunho_unico, self.owner_chat_id
                )
                self.assertIsNotNone(res)
                self.assertEqual(res["acao"], "editar")
                self.assertEqual(res["outbox_id"], "outbox-abc-123")
                self.assertEqual(res["novo_texto"], texto)

    def test_sem_pendentes_retorna_none(self):
        msg = {
            "from_me": True,
            "chat_id": self.owner_chat_id,
            "content": "sim",
        }
        res = interpretar_resposta_aprovacao_whatsapp(msg, [], self.owner_chat_id)
        self.assertIsNone(res)

    def test_multiplos_pendentes_retorna_ambiguo(self):
        pendentes = [
            {"id": "outbox-1", "content": "Msg 1"},
            {"id": "outbox-2", "content": "Msg 2"},
        ]
        msg = {
            "from_me": True,
            "chat_id": self.owner_chat_id,
            "content": "sim",
        }
        res = interpretar_resposta_aprovacao_whatsapp(msg, pendentes, self.owner_chat_id)
        self.assertIsNotNone(res)
        self.assertEqual(res["acao"], "ambiguo")
        self.assertEqual(res["quantidade"], 2)

    def test_chat_de_terceiro_ignorado_mesmo_com_comando(self):
        chat_terceiro = "5511888888888@c.us"
        for cmd in ["sim", "nao", "cancela", "texto de edicao"]:
            with self.subTest(cmd=cmd):
                msg = {
                    "from_me": True,
                    "chat_id": chat_terceiro,
                    "content": cmd,
                }
                res = interpretar_resposta_aprovacao_whatsapp(
                    msg, self.rascunho_unico, self.owner_chat_id
                )
                self.assertIsNone(res)

    def test_from_me_false_ignorado_no_self_chat(self):
        msg = {
            "from_me": False,
            "chat_id": self.owner_chat_id,
            "content": "sim",
        }
        res = interpretar_resposta_aprovacao_whatsapp(
            msg, self.rascunho_unico, self.owner_chat_id
        )
        self.assertIsNone(res)

    def test_owner_chat_id_ausente_retorna_none(self):
        msg = {
            "from_me": True,
            "chat_id": self.owner_chat_id,
            "content": "sim",
        }
        self.assertIsNone(interpretar_resposta_aprovacao_whatsapp(msg, self.rascunho_unico, None))
        self.assertIsNone(interpretar_resposta_aprovacao_whatsapp(msg, self.rascunho_unico, ""))

    def test_mensagem_sem_conteudo_retorna_none(self):
        msg = {
            "from_me": True,
            "chat_id": self.owner_chat_id,
            "content": "   ",
        }
        self.assertIsNone(
            interpretar_resposta_aprovacao_whatsapp(msg, self.rascunho_unico, self.owner_chat_id)
        )

    @mock.patch("atencao_whatsapp._obter_whatsapp_owner_chat_id")
    @mock.patch("outbox_aprovacao.listar_rascunhos")
    @mock.patch("outbox_aprovacao.aprovar_rascunho")
    def test_processar_aprovacao_outbox_executa_aprovacao(
        self, mock_aprovar, mock_listar, mock_owner_id
    ):
        mock_owner_id.return_value = self.owner_chat_id
        mock_listar.return_value = {"total": 1, "rascunhos": self.rascunho_unico}

        db = mock.MagicMock()
        msg = {
            "from_me": True,
            "chat_id": self.owner_chat_id,
            "content": "sim, pode mandar",
        }
        _processar_aprovacao_outbox(db, msg)

        mock_aprovar.assert_called_once_with(
            db, outbox_id="outbox-abc-123", aprovado_via="whatsapp"
        )

    @mock.patch("atencao_whatsapp._obter_whatsapp_owner_chat_id")
    @mock.patch("outbox_aprovacao.listar_rascunhos")
    @mock.patch("outbox_aprovacao.descartar_rascunho")
    def test_processar_aprovacao_outbox_executa_descarte(
        self, mock_descartar, mock_listar, mock_owner_id
    ):
        mock_owner_id.return_value = self.owner_chat_id
        mock_listar.return_value = {"total": 1, "rascunhos": self.rascunho_unico}

        db = mock.MagicMock()
        msg = {
            "from_me": True,
            "chat_id": self.owner_chat_id,
            "content": "descarta",
        }
        _processar_aprovacao_outbox(db, msg)

        mock_descartar.assert_called_once_with(
            db, outbox_id="outbox-abc-123"
        )

    @mock.patch("atencao_whatsapp._obter_whatsapp_owner_chat_id")
    @mock.patch("outbox_aprovacao.listar_rascunhos")
    @mock.patch("outbox_aprovacao.aplicar_edicao_rascunho")
    def test_processar_aprovacao_outbox_executa_edicao(
        self, mock_editar, mock_listar, mock_owner_id
    ):
        mock_owner_id.return_value = self.owner_chat_id
        mock_listar.return_value = {"total": 1, "rascunhos": self.rascunho_unico}

        db = mock.MagicMock()
        novo_texto = "Texto revisado pelo dono diretamente no WhatsApp"
        msg = {
            "from_me": True,
            "chat_id": self.owner_chat_id,
            "content": novo_texto,
        }
        _processar_aprovacao_outbox(db, msg)

        mock_editar.assert_called_once_with(
            db, outbox_id="outbox-abc-123", novo_texto=novo_texto
        )

    @mock.patch("atencao_whatsapp._obter_whatsapp_owner_chat_id")
    @mock.patch("outbox_aprovacao.listar_rascunhos")
    def test_processar_aprovacao_outbox_fast_path_ignora_sem_listar(
        self, mock_listar, mock_owner_id
    ):
        # Se from_me for False, nem deve buscar settings ou rascunhos
        db = mock.MagicMock()
        msg = {"from_me": False, "chat_id": self.owner_chat_id, "content": "sim"}
        _processar_aprovacao_outbox(db, msg)
        mock_owner_id.assert_not_called()
        mock_listar.assert_not_called()

        # Se chat for de terceiro, busca owner mas não lista rascunhos
        mock_owner_id.return_value = self.owner_chat_id
        msg2 = {"from_me": True, "chat_id": "terceiro@c.us", "content": "sim"}
        _processar_aprovacao_outbox(db, msg2)
        mock_listar.assert_not_called()


if __name__ == "__main__":
    unittest.main()

