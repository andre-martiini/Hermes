"""Testes da PR de custos 1 (transcrição longa + Gmail).

1. `on_long_transcription_uploaded` virou um despachante fino (256 MB): escuta o bucket padrão
   inteiro, mas só enfileira um doc em `long_transcription_jobs` para objetos de
   `long_transcriptions/`. O processamento pesado (4 GB / 2 vCPU) roda em
   `on_long_transcription_job_created` (trigger Firestore).
2. `on_gmail_watch_notification` só roda o sync quando `users.history.list` mostra mensagem
   nova no INBOX desde o history_id salvo -- o arquivamento feito pelo próprio sync não o
   redispara mais.
3. `sync_pix_emails` / `sync_boletos_gmail` saem cedo, sem varrer coleções financeiras, quando
   nenhum candidato é novo.

Os disparadores decorados são chamados via `inspect.unwrap` (mesma técnica de
test_gmail_sync_webhook.py).
"""

from __future__ import annotations

import inspect
import unittest
from unittest import mock

import main


# ---------------------------------------------------------------------------
# Firestore falso com registro de quais coleções foram varridas (stream)
# ---------------------------------------------------------------------------

class _Snap:
    def __init__(self, key, data, ref=None):
        self.id = key
        self._data = data
        self.exists = data is not None
        self.reference = ref

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, db, collection, key):
        self._db = db
        self._collection = collection
        self._key = key
        self.id = key

    @property
    def _store(self):
        return self._db.stores.setdefault(self._collection, {})

    def create(self, data):
        if self._key in self._store:
            raise RuntimeError("409 already exists")
        self._store[self._key] = dict(data)

    def get(self, transaction=None):
        return _Snap(self._key, self._store.get(self._key), self)

    def set(self, data, merge=False):
        if merge and self._key in self._store:
            self._store[self._key].update(data)
        else:
            self._store[self._key] = dict(data)
        self._db.writes.append((self._collection, self._key, dict(data)))

    def update(self, data):
        self._store.setdefault(self._key, {}).update(data)
        self._db.writes.append((self._collection, self._key, dict(data)))


class _Query:
    def __init__(self, db, collection):
        self._db = db
        self._collection = collection

    def where(self, *args, **kwargs):
        return self

    def stream(self):
        self._db.streamed.append(self._collection)
        store = self._db.stores.get(self._collection, {})
        return [_Snap(k, v, _DocRef(self._db, self._collection, k)) for k, v in list(store.items())]


class _Collection(_Query):
    def document(self, key):
        return _DocRef(self._db, self._collection, key)

    def add(self, data):
        key = f"auto{len(self._db.stores.setdefault(self._collection, {})) + 1}"
        ref = _DocRef(self._db, self._collection, key)
        ref.set(data)
        return (None, ref)


class _Db:
    def __init__(self):
        self.stores: dict[str, dict] = {}
        self.streamed: list[str] = []
        self.writes: list = []

    def collection(self, name):
        return _Collection(self, name)

    def doc_data(self, collection, key):
        return self.stores.get(collection, {}).get(key)


# ---------------------------------------------------------------------------
# 1. Transcrição longa
# ---------------------------------------------------------------------------

def _storage_event(name, bucket="gestao-hermes.firebasestorage.app", generation=1):
    event = mock.Mock()
    event.data.name = name
    event.data.bucket = bucket
    event.data.content_type = "audio/mp4"
    event.data.generation = generation
    return event


class TestDespachanteTranscricaoLonga(unittest.TestCase):
    def test_ignora_objetos_fora_de_long_transcriptions_sem_tocar_no_firestore(self):
        fn = inspect.unwrap(main.on_long_transcription_uploaded)
        with mock.patch("main.get_db") as m_db, \
             mock.patch("main.processar_transcricao_longa") as m_proc:
            fn(_storage_event("whatsapp_media/5527999999999/abc.jpg"))
        m_db.assert_not_called()
        m_proc.assert_not_called()

    def test_enfileira_job_para_long_transcriptions_sem_processar_inline(self):
        db = _Db()
        fn = inspect.unwrap(main.on_long_transcription_uploaded)
        with mock.patch("main.get_db", return_value=db), \
             mock.patch("main.processar_transcricao_longa") as m_proc:
            fn(_storage_event("long_transcriptions/uid1/tr1.m4a"))
        m_proc.assert_not_called()
        jobs = db.stores.get(main.LONG_TRANSCRIPTION_JOBS_COLLECTION, {})
        self.assertEqual(len(jobs), 1)
        job = next(iter(jobs.values()))
        self.assertEqual(job["bucket"], "gestao-hermes.firebasestorage.app")
        self.assertEqual(job["objectPath"], "long_transcriptions/uid1/tr1.m4a")
        self.assertEqual(job["contentType"], "audio/mp4")

    def test_reentrega_do_mesmo_evento_nao_duplica_job(self):
        db = _Db()
        fn = inspect.unwrap(main.on_long_transcription_uploaded)
        with mock.patch("main.get_db", return_value=db):
            fn(_storage_event("long_transcriptions/uid1/tr1.m4a"))
            fn(_storage_event("long_transcriptions/uid1/tr1.m4a"))  # não deve levantar
        self.assertEqual(len(db.stores[main.LONG_TRANSCRIPTION_JOBS_COLLECTION]), 1)

    def test_caminho_malformado_nao_enfileira(self):
        db = _Db()
        fn = inspect.unwrap(main.on_long_transcription_uploaded)
        with mock.patch("main.get_db", return_value=db):
            fn(_storage_event("long_transcriptions/solto.m4a"))
        self.assertFalse(db.stores.get(main.LONG_TRANSCRIPTION_JOBS_COLLECTION))

    def test_job_criado_chama_o_processamento_com_bucket_e_caminho(self):
        db = _Db()
        ref = db.collection(main.LONG_TRANSCRIPTION_JOBS_COLLECTION).document("j1")
        dados = {"bucket": "b1", "objectPath": "long_transcriptions/u/t.mp3"}
        ref.set(dados)
        event = mock.Mock()
        event.data = _Snap("j1", dados, ref)
        fn = inspect.unwrap(main.on_long_transcription_job_created)
        with mock.patch("main.processar_transcricao_longa") as m_proc:
            fn(event)
        m_proc.assert_called_once_with("b1", "long_transcriptions/u/t.mp3")
        self.assertEqual(db.doc_data(main.LONG_TRANSCRIPTION_JOBS_COLLECTION, "j1")["status"], "Processado")

    def test_recursos_despachante_leve_e_worker_pesado(self):
        despachante = main.on_long_transcription_uploaded.__firebase_endpoint__
        worker = main.on_long_transcription_job_created.__firebase_endpoint__
        self.assertEqual(despachante.availableMemoryMb, 256)
        self.assertEqual(worker.availableMemoryMb, 4096)
        self.assertEqual(worker.cpu, 2)
        self.assertEqual(worker.timeoutSeconds, 540)


# ---------------------------------------------------------------------------
# 2. Webhook do Gmail com filtro de delta
# ---------------------------------------------------------------------------

class _HttpError404(Exception):
    pass


def _gmail_com_history(respostas=None, erro=None):
    gs = mock.Mock()
    lista = gs.users.return_value.history.return_value.list
    if erro is not None:
        lista.return_value.execute.side_effect = erro
    else:
        lista.return_value.execute.side_effect = list(respostas)
    return gs


def _pubsub_event(history_id):
    event = mock.Mock()
    event.data.message.json = {"emailAddress": "x@example.com", "historyId": history_id}
    return event


class TestWebhookGmailDelta(unittest.TestCase):
    def _db(self, history_id=None):
        db = _Db()
        db.collection("system").document("settings").set({"gmail_watch": {"enabled": True}})
        if history_id is not None:
            db.collection("system").document(main.GMAIL_WATCH_DOC_ID).set({"history_id": history_id})
        return db

    def _rodar(self, db, gs, event, resultado_exec=None):
        fn = inspect.unwrap(main.on_gmail_watch_notification)
        with mock.patch("main.get_db", return_value=db), \
             mock.patch("main.get_gmail_service", return_value=gs), \
             mock.patch("main._executar_sync_gmail_com_lock",
                        return_value=resultado_exec or {"executado": True}) as m_exec:
            fn(event)
        return m_exec

    def test_sem_mensagem_nova_pula_o_sync_e_avanca_history_id(self):
        db = self._db("100")
        gs = _gmail_com_history([
            {"historyId": "140", "history": [{"id": "120"}], "nextPageToken": "p2"},
            {"historyId": "150", "history": [{"id": "130", "labelsRemoved": [{}]}]},
        ])
        m_exec = self._rodar(db, gs, _pubsub_event("150"))
        m_exec.assert_not_called()
        self.assertEqual(db.doc_data("system", main.GMAIL_WATCH_DOC_ID)["history_id"], "150")
        _, kwargs = gs.users.return_value.history.return_value.list.call_args_list[0]
        self.assertEqual(kwargs["startHistoryId"], "100")
        self.assertEqual(kwargs["historyTypes"], ["messageAdded"])
        self.assertEqual(kwargs["labelId"], "INBOX")
        # Paginou: a segunda chamada levou o pageToken.
        _, kwargs2 = gs.users.return_value.history.return_value.list.call_args_list[1]
        self.assertEqual(kwargs2["pageToken"], "p2")

    def test_com_mensagem_nova_roda_o_sync_e_avanca_depois(self):
        db = self._db("100")
        gs = _gmail_com_history([
            {"historyId": "150", "history": [{"id": "120", "messagesAdded": [{"message": {"id": "m1"}}]}]},
        ])
        m_exec = self._rodar(db, gs, _pubsub_event("150"))
        m_exec.assert_called_once_with(db, gs, trigger="webhook")
        self.assertEqual(db.doc_data("system", main.GMAIL_WATCH_DOC_ID)["history_id"], "150")

    def test_history_id_invalido_404_roda_o_sync_como_antes(self):
        db = self._db("100")
        gs = _gmail_com_history(erro=_HttpError404("404 Requested entity was not found"))
        m_exec = self._rodar(db, gs, _pubsub_event("999"))
        m_exec.assert_called_once()
        self.assertEqual(db.doc_data("system", main.GMAIL_WATCH_DOC_ID)["history_id"], "999")

    def test_sem_history_id_salvo_roda_o_sync_sem_chamar_history(self):
        db = self._db(None)
        gs = _gmail_com_history([])
        m_exec = self._rodar(db, gs, _pubsub_event("500"))
        m_exec.assert_called_once()
        gs.users.return_value.history.return_value.list.assert_not_called()
        self.assertEqual(db.doc_data("system", main.GMAIL_WATCH_DOC_ID)["history_id"], "500")

    def test_lock_ocupado_nao_avanca_history_id(self):
        """Se o sync não rodou, a próxima notificação precisa voltar a enxergar a mensagem."""
        db = self._db("100")
        gs = _gmail_com_history([
            {"historyId": "150", "history": [{"messagesAdded": [{"message": {"id": "m1"}}]}]},
        ])
        self._rodar(db, gs, _pubsub_event("150"),
                    resultado_exec={"executado": False, "motivo": "lock_ocupado"})
        self.assertEqual(db.doc_data("system", main.GMAIL_WATCH_DOC_ID)["history_id"], "100")

    def test_erro_no_sync_nao_avanca_history_id(self):
        db = self._db("100")
        gs = _gmail_com_history([
            {"historyId": "150", "history": [{"messagesAdded": [{"message": {"id": "m1"}}]}]},
        ])
        self._rodar(db, gs, _pubsub_event("150"),
                    resultado_exec={"executado": True, "erro": "boom"})
        self.assertEqual(db.doc_data("system", main.GMAIL_WATCH_DOC_ID)["history_id"], "100")

    def test_history_id_so_avanca_nunca_recua(self):
        db = self._db("300")
        self.assertFalse(main._avancar_gmail_history_id(db, "200"))
        self.assertEqual(db.doc_data("system", main.GMAIL_WATCH_DOC_ID)["history_id"], "300")
        self.assertFalse(main._avancar_gmail_history_id(db, "lixo"))
        self.assertTrue(main._avancar_gmail_history_id(db, 1000))
        # Comparação numérica, não lexicográfica ("1000" < "300" como string).
        self.assertEqual(db.doc_data("system", main.GMAIL_WATCH_DOC_ID)["history_id"], "1000")

    def test_payload_base64_do_pubsub_e_decodificado(self):
        import base64
        import json
        event = mock.Mock()
        event.data.message = mock.Mock(spec=["data"])
        event.data.message.data = base64.b64encode(
            json.dumps({"emailAddress": "x@example.com", "historyId": 4242}).encode()
        ).decode()
        self.assertEqual(main._history_id_da_notificacao(event), "4242")


# ---------------------------------------------------------------------------
# 3. Pix / boletos: saída cedo sem varrer coleções financeiras
# ---------------------------------------------------------------------------

def _gmail_listas(por_query: dict[str, list[str]]):
    """Mock do Gmail: messages().list(q=...) devolve os ids do primeiro prefixo que casar."""
    gs = mock.Mock()
    msgs = gs.users.return_value.messages.return_value

    def _list(userId=None, q="", maxResults=None, pageToken=None):
        req = mock.Mock()
        ids = []
        for prefixo, lista in por_query.items():
            if q.startswith(prefixo):
                ids = lista
                break
        req.execute.return_value = {"messages": [{"id": i} for i in ids]}
        return req

    msgs.list.side_effect = _list
    return gs


def _arquivados(gs):
    modify = gs.users.return_value.messages.return_value.modify
    return [kwargs["id"] for _, kwargs in modify.call_args_list]


FINANCEIRAS = {"finance_transactions", "finance_income", "income_rubrics", "bill_rubrics", "fixed_bills"}


class TestSyncPixSaidaCedo(unittest.TestCase):
    def _rodar(self, db, gs):
        with mock.patch("main.get_db", return_value=db), \
             mock.patch("main.log_to_firestore") as m_log, \
             mock.patch("main.emit_notification_backend"), \
             mock.patch("main.cleanup_retroactive_pix_duplicates") as m_cleanup:
            main.sync_pix_emails(gs, mock.Mock(), [])
        # sync_pix_emails engole exceções num log "ERRO PIX": garante que nenhum teste passe
        # por ter estourado no meio.
        mensagens = [str(c.args[2]) for c in m_log.call_args_list]
        self.assertFalse([m for m in mensagens if "ERRO PIX" in m], mensagens)
        return m_cleanup

    def test_todos_os_candidatos_ja_processados_nao_le_colecao_financeira(self):
        db = _Db()
        db.collection("system").document("processed_emails").set({"ids": ["a", "b", "c"]})
        gs = _gmail_listas({"in:inbox": ["a"], "newer_than:3d": ["a", "b", "c"]})
        m_cleanup = self._rodar(db, gs)
        self.assertFalse(FINANCEIRAS.intersection(db.streamed), db.streamed)
        m_cleanup.assert_not_called()
        # Só o que ainda está no INBOX é arquivado de novo.
        self.assertEqual(_arquivados(gs), ["a"])
        gs.users.return_value.messages.return_value.get.assert_not_called()

    def test_duas_buscas_inbox_e_ultimos_3_dias(self):
        db = _Db()
        db.collection("system").document("processed_emails").set({"ids": []})
        gs = _gmail_listas({})
        self._rodar(db, gs)
        queries = [kw["q"] for _, kw in gs.users.return_value.messages.return_value.list.call_args_list]
        self.assertTrue(any(q.startswith("in:inbox ") for q in queries), queries)
        self.assertTrue(any(q.startswith("newer_than:3d ") for q in queries), queries)
        self.assertTrue(all("after:2026/02/01" in q for q in queries))

    def test_ignorados_sem_valor_tambem_nao_forcam_o_caminho_caro(self):
        db = _Db()
        db.collection("system").document("processed_emails").set(
            {"ids": ["a"], main.PIX_IGNORADOS_FIELD: ["x"]}
        )
        gs = _gmail_listas({"in:inbox": ["a", "x"], "newer_than:3d": []})
        self._rodar(db, gs)
        self.assertFalse(FINANCEIRAS.intersection(db.streamed))
        # O e-mail sem valor não é arquivado (mesmo comportamento de antes).
        self.assertEqual(_arquivados(gs), ["a"])

    def test_ja_lancado_fora_de_processed_ids_e_registrado_sem_limpeza(self):
        db = _Db()
        db.collection("system").document("processed_emails").set({"ids": ["a"]})
        db.collection("finance_transactions").document("t1").set(
            {"description": "Pix: x", "amount": 10.0, "date": "2026-09-20T10:00:00+00:00",
             "google_message_id": "b"}
        )
        gs = _gmail_listas({"in:inbox": [], "newer_than:3d": ["a", "b"]})
        m_cleanup = self._rodar(db, gs)
        self.assertIn("finance_transactions", db.streamed)
        self.assertEqual(db.doc_data("system", "processed_emails")["ids"], ["a", "b"])
        m_cleanup.assert_not_called()  # nada inserido nesta rodada
        # Nenhum dos dois está no INBOX: nada a arquivar.
        self.assertEqual(_arquivados(gs), [])

    def test_sem_valor_vai_para_ignorados_e_nao_e_arquivado(self):
        db = _Db()
        db.collection("system").document("processed_emails").set({"ids": []})
        gs = _gmail_listas({"in:inbox": ["n1"], "newer_than:3d": []})
        gs.users.return_value.messages.return_value.get.return_value.execute.return_value = {
            "internalDate": "1790000000000", "snippet": "Seu pagamento foi agendado",
            "payload": {"headers": [{"name": "Subject", "value": "Pagamento"}, {"name": "From", "value": "banco@x"}]},
        }
        m_cleanup = self._rodar(db, gs)
        self.assertEqual(db.doc_data("system", "processed_emails")[main.PIX_IGNORADOS_FIELD], ["n1"])
        self.assertEqual(db.doc_data("system", "processed_emails")["ids"], [])
        self.assertEqual(_arquivados(gs), [])
        m_cleanup.assert_not_called()

    def test_pix_novo_lancado_roda_a_limpeza_retroativa(self):
        db = _Db()
        db.collection("system").document("processed_emails").set({"ids": ["velho"]})
        gs = _gmail_listas({"in:inbox": ["p1"], "newer_than:3d": ["p1"]})
        gs.users.return_value.messages.return_value.get.return_value.execute.return_value = {
            "internalDate": "1790000000000", "snippet": "Você fez um Pix de R$ 51,86",
            "payload": {"headers": [{"name": "Subject", "value": "Pix enviado"}, {"name": "From", "value": "banco@x"}]},
        }
        m_cleanup = self._rodar(db, gs)
        m_cleanup.assert_called_once()
        lancados = list(db.stores["finance_transactions"].values())
        self.assertEqual(len(lancados), 1)
        self.assertAlmostEqual(lancados[0]["amount"], 51.86)
        self.assertEqual(db.doc_data("system", "processed_emails")["ids"], ["velho", "p1"])
        self.assertEqual(_arquivados(gs), ["p1"])


class TestSyncBoletosSaidaCedo(unittest.TestCase):
    def test_todos_ja_processados_nao_le_gemini_nem_fixed_bills(self):
        db = _Db()
        db.collection("system").document("processed_emails").set({"ids": ["b1", "b2"]})
        gs = mock.Mock()
        gs.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "b1"}, {"id": "b2"}]
        }
        with mock.patch("main.get_db", return_value=db), \
             mock.patch("main.log_to_firestore") as m_log, \
             mock.patch("main._cached_doc_get") as m_keys:
            main.sync_boletos_gmail(gs, mock.Mock(), [])
        m_keys.assert_not_called()
        mensagens = [str(c.args[2]) for c in m_log.call_args_list]
        self.assertTrue(any("nenhum novo" in m for m in mensagens), mensagens)
        self.assertFalse(FINANCEIRAS.intersection(db.streamed))


if __name__ == "__main__":
    unittest.main()
