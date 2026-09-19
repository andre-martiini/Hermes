"""Testes de gemini_cost_controls: tabela de preços, estimativa de custo
(raciocínio, flex, modelos que faltavam) e o fallback de contagem de tokens
para embedding. Módulo sem cobertura de testes até 14/09/2026 — ver
docs/okf/operacoes/custos.md e a ação "Investigar o Relatório Diário de Custo
do Hermes" (achados 2, 3, 4 e 6 de 04/09/2026).
"""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest import mock

import gemini_cost_controls as gcc


class _Usage:
    def __init__(self, prompt=0, output=0, total=0, cached=0, thoughts=0):
        self.prompt_token_count = prompt
        self.candidates_token_count = output
        self.total_token_count = total
        self.cached_content_token_count = cached
        self.thoughts_token_count = thoughts


class _Resp:
    def __init__(self, usage=None):
        self.usage_metadata = usage


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


class PriceTableTest(unittest.TestCase):
    def test_image_and_tts_models_are_priced(self):
        # Achado 2 de 04/09/2026: modelo fora da tabela custava zero.
        self.assertIn("gemini-3.1-flash-image", gcc._MODEL_PRICE_USD_PER_MTOK)
        self.assertIn("gemini-2.5-flash-preview-tts", gcc._MODEL_PRICE_USD_PER_MTOK)
        self.assertGreater(gcc._MODEL_PRICE_USD_PER_MTOK["gemini-3.1-flash-image"]["output"], 0)
        self.assertGreater(gcc._MODEL_PRICE_USD_PER_MTOK["gemini-2.5-flash-preview-tts"]["output"], 0)


class EstimateUsdTest(unittest.TestCase):
    def test_unknown_model_returns_none(self):
        self.assertIsNone(gcc._estimate_usd("modelo-desconhecido", {"prompt_token_count": 100}))

    def test_basic_input_output(self):
        usage = {"prompt_token_count": 1_000_000, "candidates_token_count": 1_000_000}
        # gemini-3.5-flash-lite: input 0.30 + output 2.50 = 2.80
        self.assertAlmostEqual(gcc._estimate_usd("gemini-3.5-flash-lite", usage), 2.80)

    def test_gemini_3_8_flash_introductory_price_until_2026_end(self):
        usage = {"prompt_token_count": 1_000_000, "candidates_token_count": 1_000_000}
        with mock.patch.object(gcc, "datetime") as fake:
            fake.now.return_value = datetime(2026, 12, 31, 23, 0, tzinfo=gcc.TZ)
            # input 0.75 + output 3.75
            self.assertAlmostEqual(gcc._estimate_usd("gemini-3.8-flash", usage), 4.50)

    def test_gemini_3_8_flash_standard_price_from_2027(self):
        usage = {"prompt_token_count": 1_000_000, "candidates_token_count": 1_000_000}
        with mock.patch.object(gcc, "datetime") as fake:
            fake.now.return_value = datetime(2027, 1, 1, 0, 30, tzinfo=gcc.TZ)
            # tarifa padrão: input 1.50 + output 7.50
            self.assertAlmostEqual(gcc._estimate_usd("gemini-3.8-flash", usage), 9.00)

    def test_gemini_3_8_flash_thinking_tokens_billed_as_output(self):
        usage = {"prompt_token_count": 0, "candidates_token_count": 0, "thoughts_token_count": 1_000_000}
        with mock.patch.object(gcc, "datetime") as fake:
            fake.now.return_value = datetime(2026, 9, 19, tzinfo=gcc.TZ)
            self.assertAlmostEqual(gcc._estimate_usd("gemini-3.8-flash", usage), 3.75)

    def test_thoughts_tokens_are_billed_as_output(self):
        # Achado 3 de 04/09/2026: thoughts_token_count nunca entrava na conta.
        # ai.google.dev/gemini-api/docs/thinking: "response pricing is the sum
        # of output tokens and thinking tokens" — mesma taxa do output.
        usage_sem_thoughts = {"prompt_token_count": 0, "candidates_token_count": 1_000_000}
        usage_com_thoughts = {"prompt_token_count": 0, "candidates_token_count": 1_000_000, "thoughts_token_count": 500_000}
        base = gcc._estimate_usd("gemini-3.6-flash", usage_sem_thoughts)
        com_thoughts = gcc._estimate_usd("gemini-3.6-flash", usage_com_thoughts)
        # output gemini-3.6-flash = 7.50 USD/Mtok
        self.assertAlmostEqual(base, 7.50)
        self.assertAlmostEqual(com_thoughts, 7.50 * 1.5)

    def test_flex_no_longer_applies_automatic_discount(self):
        # Achado 4 de 04/09/2026, revisitado 14/09/2026: a API não confirma o
        # tier realmente aplicado, então não descontamos mais por intenção.
        usage = {"prompt_token_count": 1_000_000, "candidates_token_count": 0}
        standard = gcc._estimate_usd("gemini-3.5-flash-lite", usage, service_tier=None)
        flex = gcc._estimate_usd("gemini-3.5-flash-lite", usage, service_tier="flex")
        self.assertAlmostEqual(standard, flex)
        self.assertAlmostEqual(flex, 0.30)

    def test_cached_tokens_use_cached_price_when_available(self):
        usage = {"prompt_token_count": 1_000_000, "cached_content_token_count": 1_000_000, "candidates_token_count": 0}
        # billable_input = 0 (tudo cache); cached_input gemini-3.5-flash-lite = 0.03
        self.assertAlmostEqual(gcc._estimate_usd("gemini-3.5-flash-lite", usage), 0.03)

    def test_cached_tokens_without_published_rate_fall_back_to_input_price(self):
        # gemini-3.1-flash-image não tem cached_input publicado.
        usage = {"prompt_token_count": 1_000_000, "cached_content_token_count": 1_000_000, "candidates_token_count": 0}
        self.assertAlmostEqual(gcc._estimate_usd("gemini-3.1-flash-image", usage), 0.50)


class LogGeminiUsageTimezoneTest(unittest.TestCase):
    """O documento diário precisa ser indexado pelo dia civil em BRT, não UTC."""

    def test_writes_to_brt_dated_document(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        db = _RecordingDB()
        # 02h30 UTC de 14/09 ainda é 23h30 BRT de 13/09. Este é o caso que
        # diferencia os índices UTC e BRT.
        fixed_now = datetime(2026, 9, 14, 2, 30, tzinfo=ZoneInfo("UTC"))
        with mock.patch.object(gcc, "datetime") as dt_mock:
            dt_mock.now.side_effect = lambda tz=None: fixed_now.astimezone(tz) if tz else fixed_now
            gcc.log_gemini_usage(_Resp(_Usage(prompt=10, output=5, total=15)), model="gemini-3.5-flash-lite", feature="x", db=db)
        self.assertEqual(len(db.calls), 1)
        path, _payload, merge = db.calls[0]
        expected_day = fixed_now.astimezone(gcc.TZ).strftime("%Y-%m-%d")
        self.assertEqual(path, f"system_usage/gemini/daily/{expected_day}")
        self.assertTrue(merge)

    def test_thoughts_tokens_recorded_as_separate_field(self):
        db = _RecordingDB()
        gcc.log_gemini_usage(
            _Resp(_Usage(prompt=10, output=5, total=20, thoughts=5)),
            model="gemini-3.6-flash",
            feature="x",
            db=db,
        )
        _path, payload, _merge = db.calls[0]
        self.assertEqual(payload["tokens"]["thoughts"].value, 5)


class EmbedContentLoggedTest(unittest.TestCase):
    """Achado 6 de 04/09/2026: embedding sempre saía com custo zero."""

    def test_falls_back_to_count_tokens_when_response_has_no_usage(self):
        class _Client:
            class models:
                @staticmethod
                def embed_content(*, model, contents, **kwargs):
                    import types

                    return types.SimpleNamespace(embeddings=[])  # sem usage_metadata

                @staticmethod
                def count_tokens(*, model, contents):
                    import types

                    return types.SimpleNamespace(total_tokens=17)

        captured = {}

        def _fake_log(response, *, model, feature, db=None, extra=None, usage_override=None):
            captured["usage_override"] = usage_override
            return {}

        with mock.patch.object(gcc, "log_gemini_usage", side_effect=_fake_log):
            gcc.embed_content_logged(_Client(), model="gemini-embedding-001", contents="olá", feature="busca")

        self.assertEqual(captured["usage_override"], {"prompt_token_count": 17, "total_token_count": 17})

    def test_does_not_call_count_tokens_when_usage_already_present(self):
        # Se um dia a SDK passar a preencher usage_metadata em embed_content
        # (ex.: via Vertex), não queremos sobrescrever com o fallback.
        class _Client:
            class models:
                @staticmethod
                def embed_content(*, model, contents, **kwargs):
                    return _Resp(_Usage(prompt=9, total=9))

                @staticmethod
                def count_tokens(*, model, contents):
                    raise AssertionError("count_tokens não deveria ser chamado")

        captured = {}

        def _fake_log(response, *, model, feature, db=None, extra=None, usage_override=None):
            captured["usage_override"] = usage_override
            return {}

        with mock.patch.object(gcc, "log_gemini_usage", side_effect=_fake_log):
            gcc.embed_content_logged(_Client(), model="gemini-embedding-001", contents="olá", feature="busca")

        # usage real (extraído de usage_metadata) preservado, sem passar pelo
        # fallback de count_tokens (que teria levantado AssertionError acima).
        self.assertEqual(captured["usage_override"]["prompt_token_count"], 9)
        self.assertEqual(captured["usage_override"]["total_token_count"], 9)

    def test_count_input_tokens_free_never_raises(self):
        class _Boom:
            def count_tokens(self, *, model, contents):
                raise RuntimeError("indisponível")

        self.assertEqual(gcc.count_input_tokens_free(_Boom(), model="m", contents="c"), 0)


if __name__ == "__main__":
    unittest.main()
