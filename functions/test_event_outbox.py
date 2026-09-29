"""Testes de `event_outbox.py` — wiring Firestore do outbox de eventos puro
(`autonomy/events.py`/`autonomy/outbox.py`, P05 sub-entregas 1/N e 5/N; este
módulo é a primeira sub-entrega que persiste/despacha uma entrada de
verdade, passo 3 do pacote).

Fake de Firestore mínimo em memória, mesmo estilo de `_FakeSweepDb`/
`_FakeSweepQuery`/`_FakeSweepSnap` de `test_mcp_jobs.py`
(`TestSweepMcpJobsTravadosCore`), estendido para também suportar
`collection().document(id).get()/.set()` — `registrar_evento_outbox` usa
esse caminho, o dispatcher usa o caminho de query/stream.
"""

import unittest
from datetime import datetime, timedelta, timezone

import event_outbox
from autonomy.events import CategoriaEvento, montar_evento
from autonomy.outbox import EstadoOutbox, criar_entrada, registrar_falha

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


class _RngFixo:
    def __init__(self, valor):
        self._valor = valor

    def uniform(self, a, b):
        return self._valor


class TestRegistrarEventoOutbox(unittest.TestCase):
    def test_grava_entrada_nova_pendente(self):
        db = _FakeDb()
        evento = _evento()
        criou = event_outbox.registrar_evento_outbox(db, evento, agora=_AGORA)
        self.assertTrue(criou)
        doc = db._store[evento.event_id]
        self.assertEqual(doc["estado"], EstadoOutbox.PENDENTE.value)
        self.assertEqual(doc["tentativas"], 0)
        self.assertEqual(doc["fonte_colecao"], "whatsapp_digests")
        self.assertEqual(doc["fonte_doc_id"], "digest-1")

    def test_e_idempotente_por_event_id(self):
        db = _FakeDb()
        evento = _evento()
        event_outbox.registrar_evento_outbox(db, evento, agora=_AGORA)
        # Simula uma entrada já em progresso (despachada) -- uma segunda
        # chamada com o MESMO evento (reentrega) não pode reiniciar isso.
        db._store[evento.event_id]["estado"] = EstadoOutbox.ENVIADO.value
        depois = _AGORA + timedelta(minutes=5)
        criou_de_novo = event_outbox.registrar_evento_outbox(db, evento, agora=depois)
        self.assertFalse(criou_de_novo)
        self.assertEqual(db._store[evento.event_id]["estado"], EstadoOutbox.ENVIADO.value)

    def test_duas_ocorrencias_distintas_geram_entradas_distintas(self):
        db = _FakeDb()
        evento1 = _evento(occurred_at=_AGORA)
        evento2 = _evento(occurred_at=_AGORA + timedelta(minutes=10))
        event_outbox.registrar_evento_outbox(db, evento1, agora=_AGORA)
        event_outbox.registrar_evento_outbox(db, evento2, agora=_AGORA)
        self.assertEqual(len(db._store), 2)


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
