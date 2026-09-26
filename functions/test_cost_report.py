"""Testes de cost_report: parsing da API do BigQuery, descoberta da tabela,
agregação (média 7d, mês, projeção, alertas) e formatação da mensagem."""

from __future__ import annotations

import sys
import types
import unittest
import unittest.mock
from datetime import date

# cost_report importa firebase_functions no topo (decorador do scheduler).
# Se o SDK não estiver instalado no ambiente de teste, injeta um stub mínimo.
try:  # pragma: no cover
    import firebase_functions  # noqa: F401
except Exception:  # pragma: no cover
    _ff = types.ModuleType("firebase_functions")

    class _Opt:
        class MemoryOption:
            MB_256 = "MB_256"
            MB_512 = "MB_512"

    class _Sched:
        class ScheduledEvent:  # noqa: D401
            pass

        @staticmethod
        def on_schedule(**_kwargs):
            def deco(fn):
                return fn

            return deco

    _ff.options = _Opt
    _ff.scheduler_fn = _Sched
    sys.modules["firebase_functions"] = _ff

import cost_report as cr


class _FakeBQ:
    """Devolve respostas por trecho da consulta."""

    def __init__(self, project="gestao-hermes"):
        self.project = project
        self.queries = []

    def query(self, sql):
        self.queries.append(sql)
        if "INFORMATION_SCHEMA.TABLES" in sql:
            return [
                {"table_schema": "billing_export", "table_name": "gcp_billing_export_resource_v1_01DE18_FD9D0A_4CF875"},
                {"table_schema": "billing_export", "table_name": "gcp_billing_export_v1_01DE18_FD9D0A_4CF875"},
            ]
        raise AssertionError(f"consulta inesperada: {sql}")


class RowsToDictsTest(unittest.TestCase):
    def test_converts_schema_and_rows_with_types(self):
        payload = {
            "schema": {"fields": [{"name": "servico", "type": "STRING"}, {"name": "custo", "type": "FLOAT"}, {"name": "n", "type": "INTEGER"}]},
            "rows": [
                {"f": [{"v": "Gemini API"}, {"v": "2.5"}, {"v": "3"}]},
                {"f": [{"v": None}, {"v": None}, {"v": "0"}]},
            ],
        }
        rows = cr.rows_to_dicts(payload)
        self.assertEqual(rows[0], {"servico": "Gemini API", "custo": 2.5, "n": 3})
        self.assertEqual(rows[1], {"servico": None, "custo": None, "n": 0})

    def test_empty_payload(self):
        self.assertEqual(cr.rows_to_dicts({}), [])


class DiscoveryTest(unittest.TestCase):
    def test_prefers_resource_table_and_keeps_standard(self):
        bq = _FakeBQ()
        tables = cr.discover_billing_tables(bq, "US")
        self.assertEqual(tables["standard"], "gestao-hermes.billing_export.gcp_billing_export_v1_01DE18_FD9D0A_4CF875")
        self.assertEqual(tables["resource"], "gestao-hermes.billing_export.gcp_billing_export_resource_v1_01DE18_FD9D0A_4CF875")
        self.assertIn("`region-us`.INFORMATION_SCHEMA.TABLES", bq.queries[0])
        self.assertIn("LIKE 'gcp_billing_export%'", bq.queries[0])

    def test_queries_filter_project_and_day(self):
        class _Echo(_FakeBQ):
            def query(self, sql):
                self.queries.append(sql)
                return []

        bq = _Echo()
        cr.query_day_by_service_sku(bq, "p.d.t", "gestao-hermes", date(2026, 9, 8))
        cr.query_daily_totals(bq, "p.d.t", "gestao-hermes", date(2026, 9, 8))
        cr.query_cpu_by_function(bq, "p.d.r", "gestao-hermes", date(2026, 9, 8))
        for sql in bq.queries:
            self.assertIn("project.id = 'gestao-hermes'", sql)
            self.assertIn("'America/Sao_Paulo'", sql)
        self.assertIn("= '2026-09-08'", bq.queries[0])
        self.assertIn("BETWEEN '2026-08-08' AND '2026-09-08'", bq.queries[1])
        self.assertIn("resource.name", bq.queries[2])


class SummarizeTest(unittest.TestCase):
    def _rows(self):
        return [
            {"servico": "App Engine", "sku": "Cloud Firestore Read Ops", "custo": 3.0},
            {"servico": "Cloud Run Functions", "sku": "Cloud Run functions CPU (Request-based billing) in us-central1", "custo": 2.8},
            {"servico": "Gemini API", "sku": "Generate content input token count gemini 3.5 flash lite text", "custo": 2.0},
            {"servico": "Gemini API", "sku": "Generate content output token count gemini 3.5 flash lite text", "custo": 1.2},
            {"servico": "Cloud Scheduler", "sku": "Jobs", "custo": 0.3},
        ]

    def test_totals_average_month_and_projection(self):
        day = date(2026, 9, 8)
        totals = {f"2026-09-0{d}": 10.0 for d in range(1, 8)}  # 01..07 = R$ 10/dia
        totals["2026-09-08"] = 9.3
        totals["2026-08-30"] = 99.0  # fora do mês: não entra no acumulado
        s = cr.summarize_gcp(self._rows(), totals, day, monthly_budget=200.0)
        self.assertAlmostEqual(s["total_day"], 9.3)
        self.assertAlmostEqual(s["avg7"], 10.0)
        self.assertAlmostEqual(s["month_to_date"], 79.3)
        self.assertAlmostEqual(s["projection"], 79.3 / 8 * 30)
        self.assertTrue(s["over_budget"])  # 297 > 200
        self.assertFalse(s["spike"])
        self.assertEqual(s["top_services"][0], ("Gemini API", 3.2))  # 2.0 + 1.2 agregado por serviço
        self.assertEqual(s["top_services"][1], ("App Engine", 3.0))
        self.assertEqual(len(s["top_skus"]), 5)

    def test_spike_detection(self):
        day = date(2026, 9, 8)
        totals = {f"2026-09-0{d}": 2.0 for d in range(1, 8)}
        totals["2026-09-08"] = 9.3
        s = cr.summarize_gcp(self._rows(), totals, day, monthly_budget=500.0)
        self.assertTrue(s["spike"])
        self.assertFalse(s["over_budget"])

    def test_no_history_means_no_spike(self):
        s = cr.summarize_gcp(self._rows(), {"2026-09-08": 9.3}, date(2026, 9, 8), 200.0)
        self.assertFalse(s["spike"])
        self.assertAlmostEqual(s["avg7"], 0.0)


class FormatTest(unittest.TestCase):
    def test_brl_formatting(self):
        self.assertEqual(cr.brl(1234.5), "R$ 1.234,50")
        self.assertEqual(cr.brl(0), "R$ 0,00")

    def test_format_ai_block_labels_its_own_day(self):
        gemini = {"estimated_usd": 1.25, "calls": 40, "tokens": {"total": 900000, "input": 800000, "output": 100000}}
        lines = cr.format_ai_block(gemini, None, usd_brl=5.0, day=date(2026, 9, 9))
        self.assertIn("🤖 <b>IA — 09/09 (parcial, até agora)</b>", lines)
        self.assertIn("  • Gemini: US$ 1.25 (~R$ 6,25) | 40 chamadas | 900.000 tokens", lines)

    def test_build_message_full(self):
        # GCP (day) e IA/Firestore (today) são propositalmente dias diferentes
        # aqui, para provar que cada bloco é rotulado com a sua própria data
        # (a causa raiz do bug de rotulagem corrigido em 17/09/2026).
        day = date(2026, 9, 8)
        today = date(2026, 9, 9)
        summary = {
            "total_day": 9.3, "avg7": 10.0, "month_to_date": 79.3, "projection": 297.4,
            "monthly_budget": 200.0,
            "top_services": [("App Engine", 3.0), ("Gemini API", 3.2)],
            "top_skus": [("App Engine", "Cloud Firestore Read Ops", 3.0)],
            "spike": False, "over_budget": True,
        }
        gemini = {"estimated_usd": 1.25, "calls": 40, "tokens": {"total": 900000, "input": 800000, "output": 100000}}
        msg = cr.build_message(
            day, summary, [{"function_name": "scheduled-sync", "custo": 1.1}], gemini, None,
            ["Firestore medido (backend): 120.000 leituras | 3.000 escritas | 900 consultas"], usd_brl=5.0,
            today=today,
        )
        self.assertIn("Custos do Gaspar — 08/09/2026", msg)
        self.assertIn("⚠️ Projeção do mês (R$ 297,40) acima do orçamento (R$ 200,00)", msg)
        self.assertIn("GCP 08/09</b>: R$ 9,30 | média 7d: R$ 10,00", msg)
        self.assertIn("Mês: R$ 79,30 de R$ 200,00 | projeção: R$ 297,40", msg)
        self.assertIn("Firestore Read Ops: R$ 3,00", msg)
        self.assertIn("Serviços: Firestore R$ 3,00 · Gemini R$ 3,20", msg)
        self.assertIn("scheduled-sync: R$ 1,10", msg)
        # Cabeçalho geral e bloco GCP usam a data de ontem (day)...
        self.assertIn("Custos do Gaspar — 08/09/2026", msg)
        # ...enquanto IA e Firestore, dados parciais do dia corrente, usam
        # explicitamente a data de hoje (today) — não a mesma do cabeçalho.
        self.assertIn("IA — 09/09 (parcial, até agora)", msg)
        self.assertIn("Firestore por function — 09/09 (parcial, até agora)", msg)
        self.assertIn("Gemini: US$ 1.25 (~R$ 6,25) | 40 chamadas | 900.000 tokens", msg)
        self.assertNotIn("Claude", msg)
        self.assertIn("Firestore medido (backend): 120.000 leituras", msg)
        self.assertIn("~1 dia de atraso", msg)
        self.assertIn("IA e Firestore = dia corrente, parcial", msg)

    def test_build_message_without_gcp_data(self):
        msg = cr.build_message(date(2026, 9, 8), None, None, None, None, None, 5.0, gcp_error="permissão negada", today=date(2026, 9, 8))
        self.assertIn("sem dados do export para 08/09 (permissão negada)", msg)
        self.assertNotIn("⚠️", msg)

    def test_build_message_requires_today_keyword(self):
        with self.assertRaises(TypeError):
            cr.build_message(date(2026, 9, 8), None, None, None, None, None, 5.0)


class SummaryTest(unittest.TestCase):
    """Resumo curto enviado por padrão (26/09/2026)."""

    def _summary(self, **over):
        base = {
            "total_day": 10.16, "avg7": 7.07, "month_to_date": 333.94, "projection": 400.73,
            "monthly_budget": 200.0,
            "top_services": [("Cloud Run Functions", 5.48), ("App Engine", 2.97), ("Gemini API", 0.83), ("Cloud Scheduler", 0.3)],
            "top_skus": [], "spike": True, "over_budget": True,
        }
        base.update(over)
        return base

    def test_resumo_com_alertas(self):
        msg = cr.build_summary(date(2026, 9, 25), self._summary(), ai_brl=0.28)
        self.assertEqual(
            msg,
            "💰 <b>Custos do Gaspar — 25/09</b>\n"
            "Ontem: R$ 10,16 (média 7d R$ 7,07) ⚠️ 1,4× acima\n"
            "Mês: R$ 333,94 · projeção R$ 400,73 de R$ 200,00 ⚠️\n"
            "Maiores: Functions R$ 5,48 · Firestore R$ 2,97 · Gemini R$ 0,83\n"
            "IA hoje (parcial): R$ 0,28",
        )

    def test_resumo_sem_alertas_nao_tem_aviso(self):
        msg = cr.build_summary(
            date(2026, 9, 25), self._summary(total_day=7.0, spike=False, projection=150.0, over_budget=False), ai_brl=0.0,
        )
        self.assertNotIn("⚠️", msg)
        self.assertIn("Ontem: R$ 7,00 (média 7d R$ 7,07)\n", msg)
        self.assertIn("IA hoje (parcial): R$ 0,00", msg)

    def test_resumo_sem_dados_gcp_mostra_motivo_curto_e_escapado(self):
        erro = "403 <Forbidden> access denied " + "x" * 200 + "\nsegunda linha"
        msg = cr.build_summary(date(2026, 9, 25), None, ai_brl=1.5, gcp_error=erro)
        self.assertIn("☁️ GCP: sem dados de 25/09 (403 &lt;Forbidden&gt; access denied", msg)
        self.assertNotIn("segunda linha", msg)
        self.assertNotIn("Ontem:", msg)
        self.assertIn("IA hoje (parcial): R$ 1,50", msg)
        self.assertLess(len(msg), 300)

    def test_resumo_sem_dados_gcp_e_sem_erro(self):
        msg = cr.build_summary(date(2026, 9, 25), None, ai_brl=0.0)
        self.assertIn("☁️ GCP: sem dados de 25/09\n", msg)

    def test_ia_hoje_soma_gemini_openai_video_e_imagens(self):
        total = cr.ai_today_brl(5.0, {"estimated_usd": 0.1}, None, {"estimated_usd": 0.2}, {"estimated_usd": 0.05})
        self.assertAlmostEqual(total, 1.75)

    def test_truncamento_corta_em_fim_de_linha(self):
        texto = "\n".join(f"<b>linha {i}</b> " + "y" * 60 for i in range(200))
        cortado = cr.truncate_for_telegram(texto)
        self.assertLessEqual(len(cortado), 4096)
        self.assertTrue(cortado.endswith("… (cortado)"))
        corpo = cortado.rsplit("\n", 1)[0]
        self.assertTrue(corpo.endswith("y"))  # a última linha mantida está inteira
        self.assertEqual(corpo.count("<b>"), corpo.count("</b>"))
        self.assertEqual(cr.truncate_for_telegram("curto"), "curto")

    def test_callback_data_cabe_em_64_bytes_e_faz_ida_e_volta(self):
        det = cr.summary_keyboard("2026-09-25")[0][0]["callback_data"]
        res = cr.detail_keyboard("2026-09-25")[0][0]["callback_data"]
        self.assertEqual(det, "custos:det:2026-09-25")
        self.assertEqual(res, "custos:res:2026-09-25")
        self.assertLessEqual(len(det.encode("utf-8")), 64)
        self.assertEqual(cr.parse_callback(det), ("det", "2026-09-25"))
        self.assertEqual(cr.parse_callback(res), ("res", "2026-09-25"))
        self.assertIsNone(cr.parse_callback("custos:det:../../x"))
        self.assertIsNone(cr.parse_callback("custos:xyz:2026-09-25"))


class GerarRelatorioTest(unittest.TestCase):
    """Integra o núcleo com Firestore e BigQuery falsos, sem rede."""

    def test_end_to_end_with_fakes(self):
        class _Snap:
            def __init__(self, data):
                self._d = data
                self.exists = data is not None

            def to_dict(self):
                return self._d

        class _DocRef:
            def __init__(self, store, path):
                self.store, self.path = store, path

            def collection(self, n):
                return _DocRef(self.store, self.path + [n])

            def document(self, n):
                return _DocRef(self.store, self.path + [n])

            def get(self):
                return _Snap(self.store.get("/".join(self.path)))

        class _DB(_DocRef):
            def __init__(self, store):
                super().__init__(store, [])

        class _BQ(_FakeBQ):
            def query(self, sql):
                self.queries.append(sql)
                if "INFORMATION_SCHEMA" in sql:
                    return [{"table_schema": "bx", "table_name": "gcp_billing_export_v1_X"}]
                if "GROUP BY servico, sku" in sql:
                    return [{"servico": "Gemini API", "sku": "tokens", "custo": 4.0, "uso": 1, "unidade": "count", "moeda": "BRL"}]
                if "GROUP BY dia" in sql:
                    return [{"dia": "2026-09-08", "custo": 4.0}, {"dia": "2026-09-07", "custo": 2.0}]
                raise AssertionError(sql)

        # now = 09/09 19h BRT: yesterday = 08/09 (bloco GCP), today = 09/09
        # (blocos de IA/Firestore). A chave de telemetria própria (system_usage)
        # é indexada pelo dia corrente (09/09) — por isso o dado de teste abaixo
        # usa 2026-09-09, não 2026-09-08: é exatamente o dia que gerar_relatorio_custos
        # de fato consulta, e é o que prova que a etiqueta "today" no relatório
        # corresponde aos dados "today" realmente lidos (a regressão do bug de
        # rotulagem corrigido em 17/09/2026).
        store = {
            "system/cost_controls": {"monthly_budget_brl": 150},
            "system_usage/gemini/daily/2026-09-09": {"estimated_usd": 0.5, "calls": 3, "tokens": {"total": 1000}},
        }
        fake_main = types.ModuleType("main")
        fake_main._cached_doc_get = lambda db, c, d: db.collection(c).document(d).get()
        fake_main._fetch_usd_brl_rate = lambda db: 5.0
        saved = sys.modules.get("main")
        sys.modules["main"] = fake_main
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            now = datetime(2026, 9, 9, 19, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
            with unittest.mock.patch.object(cr, "datetime") as dt_mock:
                dt_mock.now.return_value = now
                dt_mock.side_effect = lambda *a, **k: datetime(*a, **k)
                msg = cr.gerar_relatorio_custos(_DB(store), now=now, bq=_BQ())
                textos = cr.gerar_relatorios_custos(_DB(store), now=now, bq=_BQ())
        finally:
            if saved is not None:
                sys.modules["main"] = saved
            else:
                sys.modules.pop("main", None)
        # Cabeçalho e bloco GCP: dia anterior (08/09, o que o export do Billing tem).
        self.assertIn("Custos do Gaspar — 08/09/2026", msg)
        self.assertIn("GCP 08/09</b>: R$ 4,00", msg)
        self.assertIn("de R$ 150,00", msg)
        self.assertIn("Gemini R$ 4,00", msg)
        # Bloco de IA: dia corrente (09/09), com os dados reais lidos de
        # system_usage/gemini/daily/2026-09-09 — não "sem uso registrado".
        self.assertIn("IA — 09/09 (parcial, até agora)", msg)
        self.assertIn("Gemini: US$ 0.50", msg)
        # Resumo + detalhe: a função antiga devolve exatamente o detalhe.
        self.assertEqual(textos["detalhe"], msg)
        self.assertEqual(textos["dia"], "2026-09-08")
        self.assertIn("Custos do Gaspar — 08/09</b>", textos["resumo"])
        self.assertIn("Ontem: R$ 4,00", textos["resumo"])
        self.assertIn("Maiores: Gemini R$ 4,00", textos["resumo"])
        self.assertIn("IA hoje (parcial): R$ 2,50", textos["resumo"])  # US$ 0,50 × 5,0


if __name__ == "__main__":
    import unittest.mock  # noqa: F401

    unittest.main()
