"""Testes de `event_outbox.py` — wiring Firestore do outbox de eventos puro
(`autonomy/events.py`/`autonomy/outbox.py`, P05 sub-entregas 1/N e 5/N; este
módulo é a primeira sub-entrega que persiste/despacha uma entrada de
verdade, passo 3 do pacote).

Dois fakes de Firestore separados, cada um mínimo para o que sua classe de
teste exercita:
- `_FakeDb`/`_FakeQuery` (mesmo estilo de `_FakeSweepDb`/`_FakeSweepQuery`
  de `test_mcp_jobs.py::TestSweepMcpJobsTravadosCore`) para o dispatcher
  (`despachar_outbox_eventos_core`), que só usa `.where()/.order_by()/
  .limit()/.start_after()/.stream()` e `doc_ref.update()` fora de transação.
- `_MockDb`/`_MockTransaction` (mesmo double fiel do protocolo real de
  `google.cloud.firestore_v1.transaction.Transaction` já usado em
  `test_agent_requests.py` -- implementa `_begin/_clean_up/_commit/_rollback/
  _max_attempts/_read_only` para que o decorator real `@firestore.transactional`
  exercite o mesmo caminho de código de produção) para
  `registrar_evento_outbox_transacional`.
"""

import unittest
from datetime import datetime, timedelta, timezone

import event_outbox
from autonomy.events import CategoriaEvento, montar_evento
from autonomy.outbox import EstadoOutbox, criar_entrada, iniciar_despacho, registrar_falha

_AGORA = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)


def _evento(doc_id: str = "digest-1", occurred_at: datetime = _AGORA):
    return montar_evento(
        CategoriaEvento.MENSAGEM,
        "whatsapp_digests",
        doc_id,
        {"wa_chat_id": "chat-1", "relevancia": "acao", "n_mensagens": 3},
        occurred_at=occurred_at,
        ingested_at=_AGORA,
    )


class _FakeDocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self.id = doc_id

    def get(self):
        return _FakeDocSnap(self.id, self._store.get(self.id), self)

    def set(self, data):
        self._store[self.id] = dict(data)

    def update(self, data):
        self._store[self.id].update(data)


class _FakeDocSnap:
    def __init__(self, doc_id, data, ref):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = ref

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeQuery:
    """Suporta só o subconjunto que `despachar_outbox_eventos_core` usa:
    `.where(filter=...)`, `.order_by("__name__")`, `.limit(n)`,
    `.start_after(snap)`, `.stream()` — mesmo modelo de paginação por
    doc_id de `test_mcp_jobs.py::_FakeSweepQuery`."""

    def __init__(self, store, field=None, value=None, lim=None, ordenar=False, cursor_id=None):
        self._store = store
        self._field = field
        self._value = value
        self._limit = lim
        self._ordenar = ordenar
        self._cursor_id = cursor_id

    def _clonar(self, **overrides):
        campos = dict(field=self._field, value=self._value, lim=self._limit,
                       ordenar=self._ordenar, cursor_id=self._cursor_id)
        campos.update(overrides)
        return _FakeQuery(self._store, **campos)

    def where(self, filter=None):
        return self._clonar(field=filter.field_path, value=filter.value)

    def order_by(self, field_path):
        assert field_path == "__name__"
        return self._clonar(ordenar=True)

    def limit(self, n):
        return self._clonar(lim=n)

    def start_after(self, documento):
        return self._clonar(cursor_id=getattr(documento, "id", documento))

    def document(self, doc_id):
        return _FakeDocRef(self._store, doc_id)

    def stream(self):
        ids = [doc_id for doc_id, dados in self._store.items()
               if self._field is None or dados.get(self._field) == self._value]
        if self._ordenar:
            ids.sort()
        if self._cursor_id is not None:
            ids = [doc_id for doc_id in ids if doc_id > self._cursor_id]
        if self._limit is not None:
            ids = ids[: self._limit]
        return [_FakeDocSnap(doc_id, self._store[doc_id], _FakeDocRef(self._store, doc_id)) for doc_id in ids]


class _FakeDb:
    def __init__(self, docs=None):
        self._store = {doc_id: dict(dados) for doc_id, dados in (docs or {}).items()}

    def collection(self, nome):
        assert nome == event_outbox.COLECAO
        return _FakeQuery(self._store)


class TestEntradaDocRoundTrip(unittest.TestCase):
    def test_para_doc_e_de_doc_preserva_a_entrada(self):
        entrada = criar_entrada(_evento(), _AGORA)
        doc = event_outbox._entrada_para_doc(entrada)
        reconstruida = event_outbox._entrada_de_doc(entrada.entry_id, doc)
        self.assertEqual(reconstruida, entrada)

    def test_para_doc_descongela_payload_identificador(self):
        entrada = criar_entrada(_evento(), _AGORA)
        doc = event_outbox._entrada_para_doc(entrada)
        self.assertIsInstance(doc["payload_identificador"], dict)
        self.assertNotIsInstance(doc["payload_identificador"], type(entrada.evento.payload_identificador))

    def test_de_doc_com_estado_avancado_reflete_a_transicao(self):
        entrada = criar_entrada(_evento(), _AGORA)
        falha = registrar_falha(entrada, _AGORA, "timeout", rng=_RngFixo(0.0))
        doc = event_outbox._entrada_para_doc(falha)
        reconstruida = event_outbox._entrada_de_doc(falha.entry_id, doc)
        self.assertEqual(reconstruida.estado, EstadoOutbox.PENDENTE)
        self.assertEqual(reconstruida.tentativas, 1)
        self.assertEqual(reconstruida.ultimo_erro, "timeout")

    def test_sem_lease_doc_tem_campo_lease_none(self):
        # Achado real de revisão automática do Codex (P2) na PR da
        # sub-entrega 17/N: antes da correção, `_entrada_para_doc` nem
        # sequer tinha a chave "lease" -- documentos antigos (gravados antes
        # da sub-entrega 17/N) também não têm essa chave, e `_entrada_de_doc`
        # precisa tratar "ausente" e "None" da mesma forma (ver próximo
        # teste).
        entrada = criar_entrada(_evento(), _AGORA)
        doc = event_outbox._entrada_para_doc(entrada)
        self.assertIn("lease", doc)
        self.assertIsNone(doc["lease"])

    def test_doc_sem_chave_lease_e_lido_como_lease_none(self):
        # Simula um documento gravado ANTES desta sub-entrega (sem a chave
        # "lease" de jeito nenhum, não só None).
        entrada = criar_entrada(_evento(), _AGORA)
        doc = event_outbox._entrada_para_doc(entrada)
        del doc["lease"]
        reconstruida = event_outbox._entrada_de_doc(entrada.entry_id, doc)
        self.assertIsNone(reconstruida.lease)

    def test_em_processamento_com_lease_sobrevive_ao_round_trip(self):
        # Achado real de revisão automática do Codex (P2): antes da
        # correção, uma entrada EM_PROCESSAMENTO perdia a lease ao gravar
        # (campo omitido) e _entrada_de_doc levantava o erro de
        # OutboxEntry.__post_init__ ao reler (esse estado exige lease).
        entrada = criar_entrada(_evento(), _AGORA)
        em_processamento = iniciar_despacho(entrada, "executor-1", _AGORA)
        doc = event_outbox._entrada_para_doc(em_processamento)
        self.assertIsNotNone(doc["lease"])
        reconstruida = event_outbox._entrada_de_doc(em_processamento.entry_id, doc)
        self.assertEqual(reconstruida, em_processamento)
        self.assertEqual(reconstruida.lease.lease_token, em_processamento.lease.lease_token)
        self.assertEqual(reconstruida.lease.generation, em_processamento.lease.generation)
        self.assertEqual(reconstruida.lease.executor_id, "executor-1")
        self.assertEqual(reconstruida.lease.expires_at, em_processamento.lease.expires_at)


class _RngFixo:
    def __init__(self, valor):
        self._valor = valor

    def uniform(self, a, b):
        return self._valor


class _MockDocSnapTx:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = dict(data) if data is not None else None
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else {}


class _MockDocRefTx:
    def __init__(self, col, doc_id):
        self.col = col
        self.id = doc_id

    def get(self, transaction=None):
        return _MockDocSnapTx(self.id, self.col._docs.get(self.id))

    def set(self, data, merge=False):
        if merge and self.id in self.col._docs:
            self.col._docs[self.id].update(data)
        else:
            self.col._docs[self.id] = dict(data)


class _MockCollectionTx:
    def __init__(self, name):
        self.name = name
        self._docs: dict = {}

    def document(self, doc_id):
        return _MockDocRefTx(self, doc_id)


class _MockTransaction:
    """Double fiel do protocolo real (google.cloud.firestore_v1.transaction.
    Transaction), mesmo modelo de test_agent_requests.py::_MockTransaction:
    implementa _begin/_clean_up/_commit/_rollback/_max_attempts/_read_only
    para que o decorator real `@firestore.transactional` exercite o mesmo
    caminho de código de produção."""

    def __init__(self):
        self._read_only = False
        self._id = b"mock-tx-id"
        self._max_attempts = 5

    def get(self, doc_ref):
        return doc_ref.get()

    def set(self, doc_ref, data, merge=False):
        doc_ref.set(data, merge=merge)

    def _rollback(self):
        pass

    def _commit(self):
        pass

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = retry_id or b"mock-tx-id"


class _MockDb:
    def __init__(self):
        self._collections: dict[str, _MockCollectionTx] = {}

    def collection(self, name):
        if name not in self._collections:
            self._collections[name] = _MockCollectionTx(name)
        return self._collections[name]

    def transaction(self):
        return _MockTransaction()


class TestRegistrarEventoOutboxTransacional(unittest.TestCase):
    def test_grava_entrada_nova_pendente_e_o_efeito_junto(self):
        db = _MockDb()
        evento = _evento()
        efeito_col = db.collection("whatsapp_digests")

        criou = event_outbox.registrar_evento_outbox_transacional(
            db, evento, agora=_AGORA,
            escrever_efeito=lambda tx: tx.set(efeito_col.document("digest-1"), {"resumo": "oi"}),
        )

        self.assertTrue(criou)
        self.assertEqual(efeito_col._docs["digest-1"], {"resumo": "oi"})
        doc = db.collection(event_outbox.COLECAO)._docs[evento.event_id]
        self.assertEqual(doc["estado"], EstadoOutbox.PENDENTE.value)
        self.assertEqual(doc["tentativas"], 0)
        self.assertEqual(doc["fonte_colecao"], "whatsapp_digests")
        self.assertEqual(doc["fonte_doc_id"], "digest-1")

    def test_e_idempotente_por_event_id(self):
        db = _MockDb()
        evento = _evento()
        outbox_col = db.collection(event_outbox.COLECAO)

        event_outbox.registrar_evento_outbox_transacional(
            db, evento, agora=_AGORA, escrever_efeito=lambda tx: None,
        )
        # Simula uma entrada já em progresso (despachada) -- uma segunda
        # chamada com o MESMO evento (reentrega) não pode reiniciar isso.
        outbox_col._docs[evento.event_id]["estado"] = EstadoOutbox.ENVIADO.value
        depois = _AGORA + timedelta(minutes=5)

        criou_de_novo = event_outbox.registrar_evento_outbox_transacional(
            db, evento, agora=depois, escrever_efeito=lambda tx: None,
        )

        self.assertFalse(criou_de_novo)
        self.assertEqual(outbox_col._docs[evento.event_id]["estado"], EstadoOutbox.ENVIADO.value)

    def test_duas_ocorrencias_distintas_geram_entradas_distintas(self):
        db = _MockDb()
        evento1 = _evento(occurred_at=_AGORA)
        evento2 = _evento(occurred_at=_AGORA + timedelta(minutes=10))

        event_outbox.registrar_evento_outbox_transacional(db, evento1, agora=_AGORA, escrever_efeito=lambda tx: None)
        event_outbox.registrar_evento_outbox_transacional(db, evento2, agora=_AGORA, escrever_efeito=lambda tx: None)

        self.assertEqual(len(db.collection(event_outbox.COLECAO)._docs), 2)

    def test_efeito_que_levanta_impede_a_entrada_de_outbox_de_ser_gravada(self):
        # A escrita do efeito acontece DENTRO da transação, antes do
        # transaction.set() do outbox -- se ela levantar, nada deveria ter
        # sido persistido (mesma garantia atômica que motivou esta função:
        # ver docstring do módulo, achado real do Codex na PR #382).
        db = _MockDb()
        evento = _evento()

        def _efeito_com_erro(tx):
            raise RuntimeError("falha simulada na escrita do efeito")

        with self.assertRaises(RuntimeError):
            event_outbox.registrar_evento_outbox_transacional(
                db, evento, agora=_AGORA, escrever_efeito=_efeito_com_erro,
            )

        self.assertNotIn(evento.event_id, db.collection(event_outbox.COLECAO)._docs)


class TestDespacharOutboxEventosCore(unittest.TestCase):
    def test_entrada_pendente_e_disponivel_e_despachada(self):
        db = _FakeDb()
        entrada = criar_entrada(_evento(), _AGORA)
        db._store[entrada.entry_id] = event_outbox._entrada_para_doc(entrada)

        varridas, despachadas = event_outbox.despachar_outbox_eventos_core(db, agora=_AGORA)

        self.assertEqual((varridas, despachadas), (1, 1))
        self.assertEqual(db._store[entrada.entry_id]["estado"], EstadoOutbox.ENVIADO.value)

    def test_entrada_ainda_nao_disponivel_e_pulada(self):
        db = _FakeDb()
        entrada = criar_entrada(_evento(), _AGORA)
        com_backoff = registrar_falha(entrada, _AGORA, "timeout", rng=_RngFixo(0.0))
        db._store[entrada.entry_id] = event_outbox._entrada_para_doc(com_backoff)

        varridas, despachadas = event_outbox.despachar_outbox_eventos_core(db, agora=_AGORA)

        self.assertEqual((varridas, despachadas), (1, 0))
        # Continua PENDENTE -- só ficaria elegível depois de disponivel_em.
        self.assertEqual(db._store[entrada.entry_id]["estado"], EstadoOutbox.PENDENTE.value)

    def test_entrada_ja_terminal_nao_aparece_na_consulta(self):
        db = _FakeDb()
        entrada = criar_entrada(_evento(), _AGORA)
        doc = event_outbox._entrada_para_doc(entrada)
        doc["estado"] = EstadoOutbox.ENVIADO.value
        db._store[entrada.entry_id] = doc

        varridas, despachadas = event_outbox.despachar_outbox_eventos_core(db, agora=_AGORA)

        self.assertEqual((varridas, despachadas), (0, 0))

    def test_entrada_corrompida_e_ignorada_sem_derrubar_a_varredura(self):
        db = _FakeDb()
        boa = criar_entrada(_evento("digest-boa"), _AGORA)
        db._store[boa.entry_id] = event_outbox._entrada_para_doc(boa)
        db._store["entrada-corrompida"] = {
            "estado": EstadoOutbox.PENDENTE.value,
            "categoria": "categoria_que_nao_existe",
        }

        varridas, despachadas = event_outbox.despachar_outbox_eventos_core(db, agora=_AGORA)

        self.assertEqual((varridas, despachadas), (2, 1))
        self.assertEqual(db._store[boa.entry_id]["estado"], EstadoOutbox.ENVIADO.value)

    def test_pagina_alem_do_primeiro_lote(self):
        db = _FakeDb()
        tamanho_original = event_outbox._DESPACHO_TAMANHO_PAGINA
        event_outbox._DESPACHO_TAMANHO_PAGINA = 2
        try:
            entradas = [criar_entrada(_evento(f"digest-{i}"), _AGORA) for i in range(5)]
            for entrada in entradas:
                db._store[entrada.entry_id] = event_outbox._entrada_para_doc(entrada)

            varridas, despachadas = event_outbox.despachar_outbox_eventos_core(db, agora=_AGORA)
        finally:
            event_outbox._DESPACHO_TAMANHO_PAGINA = tamanho_original

        self.assertEqual((varridas, despachadas), (5, 5))
        for entrada in entradas:
            self.assertEqual(db._store[entrada.entry_id]["estado"], EstadoOutbox.ENVIADO.value)


if __name__ == "__main__":
    unittest.main()
