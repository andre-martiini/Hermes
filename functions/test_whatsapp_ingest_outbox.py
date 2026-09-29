"""Testes do primeiro escritor real do outbox de eventos (P05, passo 3 do
pacote): `whatsapp_ingest.py::_digest_occurred_at`/`_registrar_evento_outbox_digest`,
chamadas por `_save_whatsapp_digest` logo após gravar o digest. Não cobre
`_save_whatsapp_digest`/`triage_whatsapp_messages` inteiras (dependem de
cliente Gemini/embeddings/Firestore reais e não têm suíte própria ainda) --
só o pedaço novo desta sub-entrega.
"""

import unittest
from datetime import datetime, timezone

import event_outbox
import whatsapp_ingest
from autonomy.outbox import EstadoOutbox

_AGORA = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)


class _FakeDocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self.id = doc_id

    def get(self):
        return _FakeDocSnap(self._store.get(self.id))

    def set(self, data):
        self._store[self.id] = dict(data)


class _FakeDocSnap:
    def __init__(self, data):
        self.exists = data is not None


class _FakeCollection:
    def __init__(self, store):
        self._store = store

    def document(self, doc_id):
        return _FakeDocRef(self._store, doc_id)


class _FakeDb:
    def __init__(self):
        self._store = {}

    def collection(self, nome):
        assert nome == event_outbox.COLECAO
        return _FakeCollection(self._store)


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


class TestRegistrarEventoOutboxDigest(unittest.TestCase):
    def test_grava_uma_entrada_de_outbox_pendente(self):
        db = _FakeDb()
        messages = [{"timestamp": _AGORA}]
        whatsapp_ingest._registrar_evento_outbox_digest(
            db, "digest-1", "chat-1", messages, {"relevancia": "acao"}
        )
        self.assertEqual(len(db._store), 1)
        (doc,) = db._store.values()
        self.assertEqual(doc["estado"], EstadoOutbox.PENDENTE.value)
        self.assertEqual(doc["fonte_colecao"], whatsapp_ingest.DIGEST_COLLECTION)
        self.assertEqual(doc["fonte_doc_id"], "digest-1")
        self.assertEqual(doc["payload_identificador"]["wa_chat_id"], "chat-1")
        self.assertEqual(doc["payload_identificador"]["relevancia"], "acao")
        self.assertEqual(doc["payload_identificador"]["n_mensagens"], 1)

    def test_chamar_duas_vezes_para_o_mesmo_digest_nao_duplica(self):
        db = _FakeDb()
        messages = [{"timestamp": _AGORA}]
        whatsapp_ingest._registrar_evento_outbox_digest(db, "digest-1", "chat-1", messages, {"relevancia": "acao"})
        whatsapp_ingest._registrar_evento_outbox_digest(db, "digest-1", "chat-1", messages, {"relevancia": "acao"})
        self.assertEqual(len(db._store), 1)


if __name__ == "__main__":
    unittest.main()
