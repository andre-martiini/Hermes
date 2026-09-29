"""Testes do primeiro escritor real do outbox de eventos (P05, passo 3 do
pacote): `whatsapp_ingest.py::_digest_occurred_at`/`_montar_evento_outbox_digest`,
usadas por `_save_whatsapp_digest` para montar o `EventEnvelope` persistido
junto com o digest via `event_outbox.registrar_evento_outbox_transacional`
(ver test_event_outbox.py para a escrita transacional em si). Não cobre
`_save_whatsapp_digest`/`triage_whatsapp_messages` inteiras (dependem de
cliente Gemini/embeddings/Firestore reais e não têm suíte própria ainda) --
só o pedaço novo desta sub-entrega.
"""

import unittest
from datetime import datetime, timezone

import whatsapp_ingest
from autonomy.events import CategoriaEvento

_AGORA = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)


class TestDigestOccurredAt(unittest.TestCase):
    def test_usa_timestamp_da_ultima_mensagem(self):
        ts = datetime(2026, 9, 29, 11, 30, 0, tzinfo=timezone.utc)
        messages = [{"timestamp": datetime(2026, 9, 29, 11, 0, 0, tzinfo=timezone.utc)}, {"timestamp": ts}]
        self.assertEqual(whatsapp_ingest._digest_occurred_at(messages), ts)

    def test_timestamp_naive_vira_utc(self):
        ts_naive = datetime(2026, 9, 29, 11, 30, 0)
        messages = [{"timestamp": ts_naive}]
        resultado = whatsapp_ingest._digest_occurred_at(messages)
        self.assertEqual(resultado, ts_naive.replace(tzinfo=timezone.utc))
        self.assertIsNotNone(resultado.tzinfo)

    def test_sem_timestamp_utilizavel_cai_para_agora(self):
        antes = datetime.now(timezone.utc)
        resultado = whatsapp_ingest._digest_occurred_at([{"timestamp": "não é datetime"}])
        depois = datetime.now(timezone.utc)
        self.assertTrue(antes <= resultado <= depois)

    def test_lista_vazia_cai_para_agora(self):
        antes = datetime.now(timezone.utc)
        resultado = whatsapp_ingest._digest_occurred_at([])
        depois = datetime.now(timezone.utc)
        self.assertTrue(antes <= resultado <= depois)


class TestMontarEventoOutboxDigest(unittest.TestCase):
    def test_categoria_e_fonte(self):
        messages = [{"timestamp": _AGORA}]
        evento = whatsapp_ingest._montar_evento_outbox_digest("digest-1", "chat-1", messages, {"relevancia": "acao"})
        self.assertEqual(evento.categoria, CategoriaEvento.MENSAGEM)
        self.assertEqual(evento.fonte_colecao, whatsapp_ingest.DIGEST_COLLECTION)
        self.assertEqual(evento.fonte_doc_id, "digest-1")

    def test_relevancia_vai_para_metadata_nao_para_payload_identificador(self):
        # Achado real de revisão automática do Codex (PR #382): "relevancia"
        # é saída do modelo (não determinística entre retries da mesma
        # janela) -- se entrasse em payload_identificador, participaria do
        # hash de event_id e quebraria a dedup por reentrega.
        messages = [{"timestamp": _AGORA}]
        evento = whatsapp_ingest._montar_evento_outbox_digest("digest-1", "chat-1", messages, {"relevancia": "acao"})
        self.assertNotIn("relevancia", evento.payload_identificador)
        self.assertEqual(evento.metadata["relevancia"], "acao")

    def test_payload_identificador_tem_wa_chat_id_e_n_mensagens(self):
        messages = [{"timestamp": _AGORA}, {"timestamp": _AGORA}]
        evento = whatsapp_ingest._montar_evento_outbox_digest("digest-1", "chat-1", messages, {"relevancia": "acao"})
        self.assertEqual(evento.payload_identificador["wa_chat_id"], "chat-1")
        self.assertEqual(evento.payload_identificador["n_mensagens"], 2)

    def test_relevancia_diferente_entre_retries_nao_muda_o_event_id(self):
        messages = [{"timestamp": _AGORA}]
        evento_a = whatsapp_ingest._montar_evento_outbox_digest("digest-1", "chat-1", messages, {"relevancia": "acao"})
        evento_b = whatsapp_ingest._montar_evento_outbox_digest("digest-1", "chat-1", messages, {"relevancia": "ruido"})
        self.assertEqual(evento_a.event_id, evento_b.event_id)

    def test_occurred_at_usa_digest_occurred_at(self):
        ts = datetime(2026, 9, 29, 11, 30, 0, tzinfo=timezone.utc)
        messages = [{"timestamp": ts}]
        evento = whatsapp_ingest._montar_evento_outbox_digest("digest-1", "chat-1", messages, {})
        self.assertEqual(evento.occurred_at, ts)


if __name__ == "__main__":
    unittest.main()
