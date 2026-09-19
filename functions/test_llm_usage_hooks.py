"""Testes de llm_usage_hooks: interceptação de chamadas Gemini diretas (sem contar
duas vezes as que passam pelo wrapper), stream, embed e rótulo do chamador."""

from __future__ import annotations

import os
import sys
import types
import unittest
from unittest import mock

import llm_usage_hooks as h


class _Usage:
    def __init__(self, prompt=10, output=5, total=15):
        self.prompt_token_count = prompt
        self.candidates_token_count = output
        self.total_token_count = total
        self.cached_content_token_count = 0


class _Resp:
    def __init__(self, usage=None):
        self.usage_metadata = usage


class _FakeModels:
    """Imita google.genai.models.Models: métodos a serem interceptados."""

    def generate_content(self, *, model, contents, config=None):
        return _Resp(_Usage())

    def generate_content_stream(self, *, model, contents, config=None):
        yield _Resp(None)
        yield _Resp(_Usage(prompt=7, output=3, total=10))

    def embed_content(self, *, model, contents, config=None):
        return types.SimpleNamespace(embeddings=[])

    def count_tokens(self, *, model, contents):
        return types.SimpleNamespace(total_tokens=42)


class _RecordingDB:
    def __init__(self):
        self.calls = []

    def collection(self, n):
        return _Ref(self, [n])


class _Ref:
    def __init__(self, db, path):
        self.db, self.path = db, path

    def collection(self, n):
        return _Ref(self.db, self.path + [n])

    def document(self, n):
        return _Ref(self.db, self.path + [n])

    def set(self, payload, merge=False):
        self.db.calls.append(("/".join(self.path), payload, merge))


class GeminiHooksTest(unittest.TestCase):
    def setUp(self):
        self.db = _RecordingDB()
        h._db_factory = lambda: self.db
        self.logged = []
        self._patch = mock.patch("gemini_cost_controls.log_gemini_usage", side_effect=self._fake_log)
        self._patch.start()
        self.cls = type("Models", (_FakeModels,), {})
        self.assertTrue(h.install(models_cls=self.cls))

    def tearDown(self):
        self._patch.stop()
        h._db_factory = None

    def _fake_log(self, response, *, model, feature, db=None, extra=None, usage_override=None):
        self.logged.append({
            "model": model,
            "feature": feature,
            "db": db,
            "usage": getattr(response, "usage_metadata", None),
            "usage_override": usage_override,
        })
        return {}

    def test_install_is_idempotent(self):
        before = self.cls.generate_content
        self.assertTrue(h.install(models_cls=self.cls))
        self.assertIs(self.cls.generate_content, before)
        for name in ("generate_content", "generate_content_stream", "embed_content"):
            self.assertTrue(getattr(getattr(self.cls, name), "__wrapped_by_llm_usage_hooks__", False), name)

    def test_direct_generate_content_is_logged_with_caller_feature(self):
        def sync_pix_emails():
            return self.cls().generate_content(model="gemini-3.5-flash-lite", contents="oi")

        resp = sync_pix_emails()
        self.assertIsInstance(resp, _Resp)
        self.assertEqual(len(self.logged), 1)
        self.assertEqual(self.logged[0]["model"], "gemini-3.5-flash-lite")
        self.assertEqual(self.logged[0]["feature"], "auto:test_llm_usage_hooks_sync_pix_emails")
        self.assertIs(self.logged[0]["db"], self.db)

    def test_call_inside_logged_wrapper_is_not_double_counted(self):
        import gemini_cost_controls as gcc

        client = types.SimpleNamespace(models=self.cls())
        with mock.patch.object(gcc, "should_use_flex", return_value=False):
            gcc.generate_content_logged(client, model="gemini-3.5-flash-lite", contents="oi", feature="x", db=None)
        # só a chamada do wrapper (nosso mock de log_gemini_usage) — o hook não registrou de novo
        self.assertEqual(len(self.logged), 1)
        self.assertEqual(self.logged[0]["feature"], "x")

    def test_stream_logs_last_chunk_with_usage(self):
        chunks = list(self.cls().generate_content_stream(model="gemini-3.6-flash", contents="oi"))
        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(self.logged), 1)
        self.assertEqual(self.logged[0]["model"], "gemini-3.6-flash")
        self.assertEqual(self.logged[0]["usage"].total_token_count, 10)

    def test_embed_content_logs_call(self):
        self.cls().embed_content(model="gemini-embedding-001", contents="x")
        self.assertEqual(len(self.logged), 1)
        self.assertEqual(self.logged[0]["model"], "gemini-embedding-001")

    def test_embed_content_falls_back_to_count_tokens_when_usage_missing(self):
        # EmbedContentResponse não traz usage_metadata (achado 6 de 04/09/2026)
        # — o hook precisa contar via count_tokens (gratuito) em vez de deixar
        # a chamada sem custo estimado.
        self.cls().embed_content(model="gemini-embedding-001", contents="x")
        self.assertEqual(
            self.logged[0]["usage_override"],
            {"prompt_token_count": 42, "total_token_count": 42},
        )

    def test_hook_failure_never_breaks_caller(self):
        self._patch.stop()
        with mock.patch("gemini_cost_controls.log_gemini_usage", side_effect=RuntimeError("boom")):
            resp = self.cls().generate_content(model="m", contents="c")
        self._patch.start()
        self.assertIsInstance(resp, _Resp)

    def test_disabled_by_env(self):
        with mock.patch.dict(os.environ, {"HERMES_LLM_USAGE_HOOKS": "0"}):
            self.assertFalse(h.install(models_cls=type("M2", (_FakeModels,), {})))


class CallerLabelTest(unittest.TestCase):
    def test_label_skips_internal_modules(self):
        def send_message():
            return h.caller_label()

        self.assertEqual(send_message(), "test_llm_usage_hooks_send_message")

    def test_safe_key(self):
        self.assertEqual(h._safe("a.b-c/d"), "a_b_c_d")
        self.assertEqual(h._safe(""), "unknown")

if __name__ == "__main__":
    unittest.main()
