"""Testes dos detectores reativos de WhatsApp (functions/atencao_whatsapp.py)."""

from datetime import datetime, timezone
import unittest

from atencao_whatsapp import (
    ESTADO_PROMESSA_ABERTA,
    ESTADO_PROMESSA_VENCIDA,
    TIPO_AUDIO_RELEVANTE,
    TIPO_PROMESSA_SEM_RETORNO,
    avaliar_audio,
    avaliar_promessas_vencidas,
    decidir_acao_mensagem_from_me,
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


if __name__ == "__main__":
    unittest.main()
