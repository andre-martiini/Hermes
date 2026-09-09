"""Relatório diário de custos do Hermes no Telegram (DEV-2026-0003, PR 1).

Substitui ``relatorio_diario_custo_gemini`` (20h30, só tokens Gemini) por um
relatório às 19h BRT com quatro blocos:

1. **GCP real** (export do Cloud Billing no BigQuery, dia anterior — o export
   chega com até ~1 dia de atraso): total do dia, média dos 7 dias anteriores,
   acumulado e projeção do mês contra ``system/cost_controls.monthly_budget_brl``
   (padrão R$ 200), top serviços e top SKUs; CPU por function quando o export
   detalhado ("Custo detalhado de uso") estiver ligado.
2. **IA por telemetria própria** (dia corrente): Gemini (``system_usage/gemini``),
   Claude (``system_usage/claude`` — criado no PR 2), OpenAI (``system_usage/openai``).
3. **Firestore medido por function/coleção** (``firestore_metrics``, dia corrente).
4. Alertas: dia > 1,3× a média de 7 dias, ou projeção do mês > orçamento.

A tabela do export é descoberta sozinha via ``INFORMATION_SCHEMA.TABLES``
(prefixo ``gcp_billing_export``), preferindo a tabela ``_resource_`` (detalhada)
quando existir; pode ser fixada em ``system/cost_controls.bigquery_table`` /
``bigquery_resource_table``. Região do dataset: ``bigquery_location`` (padrão ``US``).

Acesso ao BigQuery pela API REST com a credencial padrão da function
(``google-auth`` + ``requests``, já presentes) — sem dependência nova. A service
account das functions precisa de ``roles/bigquery.jobUser`` no projeto e
``roles/bigquery.dataViewer`` no dataset do export (ver docs/okf/operacoes/custos.md).
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from firebase_functions import options, scheduler_fn

TZ = ZoneInfo("America/Sao_Paulo")
BILLING_TABLE_PREFIX = "gcp_billing_export"
DEFAULT_MONTHLY_BUDGET_BRL = 200.0
SPIKE_FACTOR = 1.3
BQ_ENDPOINT = "https://bigquery.googleapis.com/bigquery/v2"


# --------------------------------------------------------------------------- #
# BigQuery via REST
# --------------------------------------------------------------------------- #
class BigQueryRest:
    """Cliente mínimo (jobs.query síncrono) sobre a credencial padrão da function."""

    def __init__(self, project: str, session=None, timeout_ms: int = 60000):
        self.project = project
        self.timeout_ms = timeout_ms
        self._session = session

    def _get_session(self):
        if self._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            creds, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/bigquery.readonly"]
            )
            self._session = AuthorizedSession(creds)
        return self._session

    def query(self, sql: str) -> list[dict[str, Any]]:
        session = self._get_session()
        resp = session.post(
            f"{BQ_ENDPOINT}/projects/{self.project}/queries",
            json={
                "query": sql,
                "useLegacySql": False,
                "timeoutMs": self.timeout_ms,
                "maxResults": 2000,
            },
            timeout=self.timeout_ms / 1000 + 10,
        )
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("jobComplete", False):
            raise TimeoutError("Consulta BigQuery não concluiu dentro do timeout.")
        return rows_to_dicts(payload)


def rows_to_dicts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Converte o formato ``schema.fields`` + ``rows[].f[].v`` da API em dicts."""
    fields = [f["name"] for f in (payload.get("schema") or {}).get("fields") or []]
    types = [f.get("type") for f in (payload.get("schema") or {}).get("fields") or []]
    out: list[dict[str, Any]] = []
    for row in payload.get("rows") or []:
        values = [cell.get("v") for cell in row.get("f") or []]
        item: dict[str, Any] = {}
        for name, typ, value in zip(fields, types, values):
            if value is None:
                item[name] = None
            elif typ in ("FLOAT", "FLOAT64", "NUMERIC", "BIGNUMERIC"):
                item[name] = float(value)
            elif typ in ("INTEGER", "INT64"):
                item[name] = int(value)
            else:
                item[name] = value
        out.append(item)
    return out


# --------------------------------------------------------------------------- #
# Descoberta da tabela e consultas
# --------------------------------------------------------------------------- #
def discover_billing_tables(bq: BigQueryRest, location: str = "US") -> dict[str, str | None]:
    """Localiza as tabelas do export no projeto: ``standard`` e ``resource``."""
    sql = (
        f"SELECT table_schema, table_name "
        f"FROM `{bq.project}`.`region-{location.lower()}`.INFORMATION_SCHEMA.TABLES "
        f"WHERE table_name LIKE '{BILLING_TABLE_PREFIX}%' "
        f"ORDER BY table_name"
    )
    result: dict[str, str | None] = {"standard": None, "resource": None}
    for row in bq.query(sql):
        full = f"{bq.project}.{row['table_schema']}.{row['table_name']}"
        if "_resource_" in row["table_name"]:
            result["resource"] = result["resource"] or full
        else:
            result["standard"] = result["standard"] or full
    return result


def _cost_expr() -> str:
    return "SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0))"


def query_day_by_service_sku(bq: BigQueryRest, table: str, project_id: str, day: date) -> list[dict[str, Any]]:
    sql = (
        f"SELECT service.description AS servico, sku.description AS sku, "
        f"{_cost_expr()} AS custo, SUM(usage.amount) AS uso, ANY_VALUE(usage.unit) AS unidade, "
        f"ANY_VALUE(currency) AS moeda "
        f"FROM `{table}` "
        f"WHERE project.id = '{project_id}' "
        f"AND DATE(usage_start_time, 'America/Sao_Paulo') = '{day.isoformat()}' "
        f"GROUP BY servico, sku ORDER BY custo DESC"
    )
    return bq.query(sql)


def query_daily_totals(bq: BigQueryRest, table: str, project_id: str, day: date, days_back: int = 31) -> dict[str, float]:
    start = day - timedelta(days=days_back)
    sql = (
        f"SELECT DATE(usage_start_time, 'America/Sao_Paulo') AS dia, {_cost_expr()} AS custo "
        f"FROM `{table}` "
        f"WHERE project.id = '{project_id}' "
        f"AND DATE(usage_start_time, 'America/Sao_Paulo') BETWEEN '{start.isoformat()}' AND '{day.isoformat()}' "
        f"GROUP BY dia"
    )
    return {str(r["dia"]): float(r["custo"] or 0.0) for r in bq.query(sql)}


def query_cpu_by_function(bq: BigQueryRest, resource_table: str, project_id: str, day: date) -> list[dict[str, Any]]:
    sql = (
        f"SELECT IFNULL(resource.name, '(sem nome)') AS function_name, {_cost_expr()} AS custo, "
        f"SUM(usage.amount) AS uso "
        f"FROM `{resource_table}` "
        f"WHERE project.id = '{project_id}' "
        f"AND service.description LIKE 'Cloud Run%' "
        f"AND DATE(usage_start_time, 'America/Sao_Paulo') = '{day.isoformat()}' "
        f"GROUP BY function_name ORDER BY custo DESC LIMIT 8"
    )
    return bq.query(sql)


# --------------------------------------------------------------------------- #
# Agregação e formatação (puras — testáveis sem rede)
# --------------------------------------------------------------------------- #
def brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def summarize_gcp(
    rows: list[dict[str, Any]],
    daily_totals: dict[str, float],
    day: date,
    monthly_budget: float,
    top_n: int = 5,
) -> dict[str, Any]:
    """Números do bloco GCP: total do dia, média 7d, mês acumulado e projeção."""
    by_service: dict[str, float] = {}
    for r in rows:
        by_service[r["servico"] or "?"] = by_service.get(r["servico"] or "?", 0.0) + float(r["custo"] or 0.0)
    total_day = sum(by_service.values())

    prev7 = [daily_totals.get((day - timedelta(days=i)).isoformat(), 0.0) for i in range(1, 8)]
    avg7 = sum(prev7) / 7.0 if prev7 else 0.0

    month_start = day.replace(day=1)
    month_to_date = sum(v for k, v in daily_totals.items() if month_start.isoformat() <= k <= day.isoformat())
    days_in_month = (month_start.replace(month=month_start.month % 12 + 1, year=month_start.year + (1 if month_start.month == 12 else 0)) - timedelta(days=1)).day
    elapsed = max(1, day.day)
    projection = month_to_date / elapsed * days_in_month if month_to_date else 0.0

    top_services = sorted(by_service.items(), key=lambda kv: -kv[1])[:top_n]
    top_skus = sorted(rows, key=lambda r: -float(r["custo"] or 0.0))[:top_n]
    return {
        "total_day": total_day,
        "avg7": avg7,
        "month_to_date": month_to_date,
        "projection": projection,
        "monthly_budget": monthly_budget,
        "top_services": top_services,
        "top_skus": [(r["servico"], r["sku"], float(r["custo"] or 0.0)) for r in top_skus],
        "spike": avg7 > 0 and total_day > SPIKE_FACTOR * avg7,
        "over_budget": projection > monthly_budget,
    }


def format_gcp_block(summary: dict[str, Any], day: date, cpu_rows: list[dict[str, Any]] | None) -> list[str]:
    lines = [
        f"☁️ <b>GCP {day.strftime('%d/%m')}</b>: {brl(summary['total_day'])} | média 7d: {brl(summary['avg7'])}",
        f"Mês: {brl(summary['month_to_date'])} de {brl(summary['monthly_budget'])} | projeção: {brl(summary['projection'])}",
    ]
    if summary["top_services"]:
        lines.append("Serviços: " + " · ".join(f"{_service_label(s)} {brl(v)}" for s, v in summary["top_services"]))
    if summary["top_skus"]:
        lines.append("Top SKUs:")
        for _svc, sku, v in summary["top_skus"]:
            lines.append(f"  • {_short(sku)}: {brl(v)}")
    if cpu_rows:
        lines.append("Functions (Cloud Run) por serviço:")
        for r in cpu_rows[:6]:
            lines.append(f"  • {r['function_name']}: {brl(float(r['custo'] or 0.0))}")
    return lines


_SERVICE_LABELS = {
    "App Engine": "Firestore",  # o Billing fatura o Firestore sob "App Engine"
    "Cloud Run Functions": "Functions",
    "Gemini API": "Gemini",
    "Cloud Scheduler": "Scheduler",
    "Secret Manager": "Secrets",
    "Artifact Registry": "Artifact Reg.",
}


def _service_label(name: str) -> str:
    return _SERVICE_LABELS.get(name or "", (name or "?").replace("Cloud ", "", 1) if name != "Cloud Run" else "Cloud Run")


def _short(text: str, n: int = 58) -> str:
    text = (text or "").replace("Generate content ", "").replace("Cloud Run functions ", "")
    return text if len(text) <= n else text[: n - 1] + "…"


def format_ai_block(gemini: dict[str, Any] | None, claude: dict[str, Any] | None, openai: dict[str, Any] | None, usd_brl: float) -> list[str]:
    lines = ["🤖 <b>IA hoje (telemetria própria)</b>"]

    def _line(label: str, data: dict[str, Any] | None, missing: str) -> str:
        if not data:
            return f"  • {label}: {missing}"
        usd = float(data.get("estimated_usd") or 0.0)
        tokens = data.get("tokens") or {}
        total_tokens = int(tokens.get("total") or (int(tokens.get("input") or 0) + int(tokens.get("output") or 0)))
        tokens_fmt = f"{total_tokens:,}".replace(",", ".")
        return (
            f"  • {label}: US$ {usd:.2f} (~{brl(usd * usd_brl)}) | {int(data.get('calls') or 0)} chamadas | "
            f"{tokens_fmt} tokens"
        )

    lines.append(_line("Gemini", gemini, "sem uso registrado"))
    lines.append(_line("Claude", claude, "sem telemetria ainda (PR 2)"))
    lines.append(_line("OpenAI", openai, "sem uso registrado"))
    return lines


def build_message(
    day: date,
    gcp_summary: dict[str, Any] | None,
    cpu_rows: list[dict[str, Any]] | None,
    gemini: dict[str, Any] | None,
    claude: dict[str, Any] | None,
    openai: dict[str, Any] | None,
    firestore_lines: list[str] | None,
    usd_brl: float,
    gcp_error: str | None = None,
) -> str:
    lines: list[str] = []
    alerts: list[str] = []
    if gcp_summary:
        if gcp_summary["over_budget"]:
            alerts.append(f"⚠️ Projeção do mês ({brl(gcp_summary['projection'])}) acima do orçamento ({brl(gcp_summary['monthly_budget'])})")
        if gcp_summary["spike"]:
            alerts.append(f"⚠️ Dia {SPIKE_FACTOR:.1f}× acima da média de 7 dias")
    header = f"💰 <b>Custos do Hermes — {day.strftime('%d/%m/%Y')}</b>"
    lines.append(header)
    lines.extend(alerts)
    if gcp_summary:
        lines.extend(format_gcp_block(gcp_summary, day, cpu_rows))
    else:
        lines.append(f"☁️ GCP: sem dados do export para {day.strftime('%d/%m')}" + (f" ({gcp_error})" if gcp_error else ""))
    lines.append("")
    lines.extend(format_ai_block(gemini, claude, openai, usd_brl))
    if firestore_lines:
        lines.append("")
        lines.append("🗄️ <b>Firestore por function (hoje)</b>")
        lines.extend(firestore_lines)
    lines.append("")
    lines.append("Obs.: GCP = dia anterior (export do Billing tem ~1 dia de atraso; o último dia pode estar parcial). Anthropic/OpenAI/Groq/Tavily/Twilio não entram na fatura GCP.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Function agendada
# --------------------------------------------------------------------------- #
def _project_id() -> str:
    return (
        os.environ.get("GCLOUD_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("PROJECT_ID")
        or "gestao-hermes"
    )


def _usage_doc(db, provider: str, day: str) -> dict[str, Any] | None:
    try:
        snap = db.collection("system_usage").document(provider).collection("daily").document(day).get()
        return (snap.to_dict() or {}) if getattr(snap, "exists", False) else None
    except Exception:
        return None


def gerar_relatorio_custos(db, now: datetime | None = None, bq: BigQueryRest | None = None) -> str:
    """Núcleo do relatório (sem envio). Separado para teste e para regeneração manual."""
    from main import _cached_doc_get, _fetch_usd_brl_rate

    now = now or datetime.now(TZ)
    today = now.astimezone(TZ).date()
    yesterday = today - timedelta(days=1)

    cfg: dict[str, Any] = {}
    try:
        snap = _cached_doc_get(db, "system", "cost_controls")
        cfg = (snap.to_dict() or {}) if getattr(snap, "exists", False) else {}
    except Exception:
        cfg = {}
    monthly_budget = float(cfg.get("monthly_budget_brl") or DEFAULT_MONTHLY_BUDGET_BRL)
    location = str(cfg.get("bigquery_location") or "US")
    project_id = _project_id()

    gcp_summary = None
    cpu_rows = None
    gcp_error = None
    try:
        bq = bq or BigQueryRest(project_id)
        tables = {"standard": cfg.get("bigquery_table"), "resource": cfg.get("bigquery_resource_table")}
        if not tables["standard"] and not tables["resource"]:
            tables = discover_billing_tables(bq, location)
        table = tables.get("standard") or tables.get("resource")
        if not table:
            gcp_error = "nenhuma tabela gcp_billing_export encontrada"
        else:
            rows = query_day_by_service_sku(bq, table, project_id, yesterday)
            totals = query_daily_totals(bq, table, project_id, yesterday)
            gcp_summary = summarize_gcp(rows, totals, yesterday, monthly_budget)
            if tables.get("resource"):
                try:
                    cpu_rows = query_cpu_by_function(bq, tables["resource"], project_id, yesterday)
                except Exception as exc:
                    print(f"[CustosHermes] CPU por function indisponível: {exc}")
    except Exception as exc:
        gcp_error = str(exc)[:160]
        print(f"[CustosHermes] BigQuery falhou: {exc}")

    day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")  # system_usage é indexado em UTC
    gemini = _usage_doc(db, "gemini", day_key)
    claude = _usage_doc(db, "claude", day_key)
    openai = _usage_doc(db, "openai", day_key)

    firestore_lines = None
    try:
        import firestore_metrics

        fs_data = firestore_metrics.read_daily_usage(db, day_key)
        if fs_data:
            firestore_lines = firestore_metrics.format_daily_summary(fs_data, top_n=5)
    except Exception as exc:
        print(f"[CustosHermes] firestore_metrics indisponível: {exc}")

    try:
        usd_brl = float(_fetch_usd_brl_rate(db))
    except Exception:
        usd_brl = 5.30

    return build_message(yesterday, gcp_summary, cpu_rows, gemini, claude, openai, firestore_lines, usd_brl, gcp_error)


@scheduler_fn.on_schedule(
    schedule="0 19 * * *",
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_256,
    timeout_sec=120,
)
def relatorio_diario_custos(event: scheduler_fn.ScheduledEvent = None) -> None:
    """19h BRT — custos GCP (BigQuery) + IA + Firestore por function no Telegram."""
    from main import get_db, _resolve_default_telegram_chat_id
    from telegram_utils import _get_telegram_token, _send_telegram_message

    db = get_db()
    try:
        message = gerar_relatorio_custos(db)
    except Exception as exc:
        print(f"[CustosHermes] Falha ao montar relatório: {exc}")
        return
    print(f"[CustosHermes] {message}")
    chat_id = _resolve_default_telegram_chat_id(db)
    if not chat_id:
        print("[CustosHermes] Nenhum chat_id do Telegram configurado; relatório apenas nos logs.")
        return
    _send_telegram_message(_get_telegram_token(db), chat_id, message)  # parse_mode HTML
