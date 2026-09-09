"""Testes de firestore_metrics: contagem por function/coleção e flush agregado.

Não toca o Firestore real: os hooks são exercitados com objetos falsos que
imitam o formato interno do SDK (``_path``, ``_parent``, ``_write_pbs``,
``_document_references``) e o cliente do flush é injetado.
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest import mock

import firestore_metrics as fm


class _FakeCollection:
    def __init__(self, *path):
        self._path = tuple(path)


class _FakeDoc:
    def __init__(self, *path):
        self._path = tuple(path)


class _FakeQuery:
    def __init__(self, collection):
        self._parent = collection


class _FakeBatch:
    def __init__(self, refs, writes):
        self._document_references = {"/".join(r._path): r for r in refs}
        self._write_pbs = [object()] * writes


class _RecordingClient:
    """Cliente falso que registra o set(merge=True) do flush."""

    def __init__(self):
        self.calls = []

    def collection(self, name):
        return _RecordingRef(self, [name])


class _RecordingRef:
    def __init__(self, client, path):
        self._client = client
        self.path = path

    def document(self, name):
        return _RecordingRef(self._client, self.path + [name])

    def collection(self, name):
        return _RecordingRef(self._client, self.path + [name])

    def set(self, payload, merge=False):
        self._client.calls.append(("/".join(self.path), payload, merge))


def _reset_state():
    with fm._lock:
        fm._state["reads"] = fm._state["writes"] = fm._state["queries"] = 0
        fm._state["collections"] = {}
        fm._state["pending_ops"] = 0
        fm._state["last_flush"] = 1e18  # nunca "vence" por tempo durante o teste


class FirestoreMetricsTest(unittest.TestCase):
    def setUp(self):
        _reset_state()
        fm._client_factory = None
        self._env = mock.patch.dict(os.environ, {"K_SERVICE": "check-and-send-reminders"})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        fm._client_factory = None
        _reset_state()

    # ------------------------------------------------------------------ #
    def test_service_name_sanitizes_k_service(self):
        self.assertEqual(fm.service_name(), "check_and_send_reminders")

    def test_top_collection_from_doc_collection_and_query(self):
        self.assertEqual(fm.top_collection(_FakeDoc("tarefas", "abc")), "tarefas")
        self.assertEqual(fm.top_collection(_FakeDoc("system_usage", "gemini", "daily", "2026-09-08")), "system_usage")
        self.assertEqual(fm.top_collection(_FakeCollection("whatsapp_messages")), "whatsapp_messages")
        self.assertEqual(fm.top_collection(_FakeQuery(_FakeCollection("tarefas"))), "tarefas")
        self.assertEqual(fm.top_collection(object()), "unknown")

    def test_doc_get_counts_one_read_even_if_missing(self):
        fm.count_read(_FakeDoc("configuracoes", "geral"))
        snap = fm.snapshot()
        self.assertEqual(snap["reads"], 1)
        self.assertEqual(snap["collections"]["configuracoes"]["reads"], 1)

    def test_counting_stream_counts_each_document(self):
        query = _FakeQuery(_FakeCollection("tarefas"))
        fm.count_query(query)
        stream = fm._CountingStream(iter(["a", "b", "c"]), query)
        self.assertEqual(list(stream), ["a", "b", "c"])
        snap = fm.snapshot()
        self.assertEqual(snap["queries"], 1)
        self.assertEqual(snap["reads"], 3)
        self.assertEqual(snap["collections"]["tarefas"]["reads"], 3)

    def test_empty_query_still_costs_one_read(self):
        query = _FakeQuery(_FakeCollection("scheduled_notifications"))
        fm.count_query(query)
        list(fm._CountingStream(iter([]), query))
        snap = fm.snapshot()
        self.assertEqual(snap["reads"], 1)
        self.assertEqual(snap["collections"]["scheduled_notifications"]["reads"], 1)

    def test_counting_stream_delegates_unknown_attributes(self):
        class _Inner:
            def __iter__(self):
                return iter([])

            def __next__(self):
                raise StopIteration

            def get_explain_metrics(self):
                return "metrics"

        stream = fm._CountingStream(_Inner(), _FakeQuery(_FakeCollection("x")))
        self.assertEqual(stream.get_explain_metrics(), "metrics")

    def test_batch_commit_attributes_writes_per_collection(self):
        batch = _FakeBatch(
            refs=[_FakeDoc("tarefas", "1"), _FakeDoc("tarefas", "2"), _FakeDoc("system", "sync")],
            writes=3,
        )
        fm._count_batch_writes(batch)
        snap = fm.snapshot()
        self.assertEqual(snap["writes"], 3)
        self.assertEqual(snap["collections"]["tarefas"]["writes"], 2)
        self.assertEqual(snap["collections"]["system"]["writes"], 1)

    def test_batch_commit_without_refs_goes_to_batch_bucket(self):
        batch = _FakeBatch(refs=[], writes=4)
        fm._count_batch_writes(batch)
        snap = fm.snapshot()
        self.assertEqual(snap["writes"], 4)
        self.assertEqual(snap["collections"]["batch"]["writes"], 4)

    def test_internal_operations_are_not_counted(self):
        fm._internal.active = True
        try:
            fm.count_write(_FakeDoc("system_usage", "firestore"))
        finally:
            fm._internal.active = False
        self.assertEqual(fm.snapshot()["writes"], 0)

    # ------------------------------------------------------------------ #
    def test_flush_writes_single_merge_with_increments_and_resets(self):
        client = _RecordingClient()
        fm._client_factory = lambda: client
        fm.count_read(_FakeDoc("tarefas", "1"), 5)
        fm.count_write(_FakeDoc("system", "sync"), 2)
        fm.count_query(_FakeQuery(_FakeCollection("tarefas")))

        self.assertTrue(fm.flush())

        self.assertEqual(len(client.calls), 1)
        path, payload, merge = client.calls[0]
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.assertEqual(path, f"system_usage/firestore/daily/{day}")
        self.assertTrue(merge)
        from google.cloud.firestore_v1 import Increment

        self.assertIsInstance(payload["total"]["reads"], Increment)
        self.assertEqual(payload["total"]["reads"].value, 5)
        self.assertEqual(payload["total"]["writes"].value, 2)
        self.assertEqual(payload["total"]["queries"].value, 1)
        self.assertIn("check_and_send_reminders", payload["services"])
        self.assertEqual(payload["services"]["check_and_send_reminders"]["reads"].value, 5)
        self.assertEqual(payload["collections"]["tarefas"]["reads"].value, 5)
        self.assertEqual(payload["collections"]["system"]["writes"].value, 2)
        self.assertIn("updated_at", payload)

        snap = fm.snapshot()
        self.assertEqual((snap["reads"], snap["writes"], snap["queries"], snap["pending_ops"]), (0, 0, 0, 0))

    def test_flush_with_nothing_pending_writes_nothing(self):
        client = _RecordingClient()
        fm._client_factory = lambda: client
        self.assertFalse(fm.flush())
        self.assertEqual(client.calls, [])

    def test_flush_failure_keeps_counters_for_retry(self):
        def _boom():
            raise RuntimeError("firestore indisponível")

        fm._client_factory = _boom
        fm.count_read(_FakeDoc("tarefas", "1"), 3)
        self.assertFalse(fm.flush())
        snap = fm.snapshot()
        self.assertEqual(snap["reads"], 3)
        self.assertEqual(snap["pending_ops"], 3)

    def test_bump_flushes_when_ops_threshold_reached(self):
        client = _RecordingClient()
        fm._client_factory = lambda: client
        with mock.patch.object(fm, "FLUSH_OPS_THRESHOLD", 10):
            fm.count_read(_FakeDoc("tarefas", "1"), 10)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(fm.snapshot()["pending_ops"], 0)

    # ------------------------------------------------------------------ #
    def test_install_patches_sdk_idempotently(self):
        from google.cloud.firestore_v1 import Client, DocumentReference, Query, Transaction, WriteBatch

        self.assertTrue(fm.install())
        self.assertTrue(fm.install())  # segunda chamada não empilha wrappers
        for cls, name in [
            (DocumentReference, "get"),
            (DocumentReference, "set"),
            (DocumentReference, "update"),
            (DocumentReference, "delete"),
            (DocumentReference, "create"),
            (Query, "stream"),
            (Client, "get_all"),
            (WriteBatch, "commit"),
            (Transaction, "_commit"),
        ]:
            self.assertTrue(
                getattr(getattr(cls, name), "__wrapped_by_firestore_metrics__", False),
                f"{cls.__name__}.{name} não foi interceptado",
            )

    def test_format_daily_summary_ranks_services_and_collections(self):
        data = {
            "total": {"reads": 1500, "writes": 20, "queries": 7},
            "services": {
                "scheduled_sync": {"reads": 1000, "writes": 15, "queries": 3},
                "check_and_send_reminders": {"reads": 500, "writes": 5, "queries": 4},
            },
            "collections": {"tarefas": {"reads": 1200, "writes": 10}, "system": {"reads": 300, "writes": 10}},
        }
        lines = fm.format_daily_summary(data, top_n=1)
        self.assertIn("1.500 leituras", lines[0])
        self.assertTrue(any("scheduled_sync: 1.000 L / 15 E" in l for l in lines))
        self.assertTrue(any("tarefas: 1.200 L" in l for l in lines))
        self.assertFalse(any("check_and_send_reminders" in l for l in lines))


if __name__ == "__main__":
    unittest.main()
