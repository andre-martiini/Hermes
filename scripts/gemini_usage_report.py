"""
Readout da telemetria de uso do Gemini no Hermes.

Lê os agregados diários gravados por `gemini_cost_controls.log_gemini_usage` em
`system_usage/gemini/daily/{AAAA-MM-DD}` e mostra onde o custo se concentra
(por feature e por modelo), para guiar decisões de economia.

Uso:
  python scripts/gemini_usage_report.py --days 7
  python scripts/gemini_usage_report.py --date 2026-06-27
  python scripts/gemini_usage_report.py --days 30 --credentials /caminho/sa.json

Risco zero: o script é somente-leitura, não altera nenhum documento.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CREDENTIALS = ROOT / "firebase_service_account_key.json"

# Preços (USD por 1M tokens) — espelham gemini_cost_controls._MODEL_PRICE_USD_PER_MTOK.
# Usados apenas como fallback de estimativa quando o doc não traz estimated_usd.
PRICE_PER_MTOK = {
    "gemini-3.6-flash": {"input": 1.50, "output": 7.50, "cached_input": 0.15},
    "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50, "cached_input": 0.03},
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00, "cached_input": 0.15},
    "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50, "cached_input": 0.025},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40, "cached_input": 0.01},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50, "cached_input": 0.03},
    "gemini-3.1-pro-preview": {"input": 2.00, "output": 12.00, "cached_input": 0.20},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00, "cached_input": 0.125},
    "gemini-embedding-001": {"input": 0.15, "output": 0.00, "cached_input": 0.00},
}


def init_firebase(credentials_path: Path):
    if firebase_admin._apps:
        return firestore.client()
    if credentials_path.exists():
        cred = credentials.Certificate(str(credentials_path))
        firebase_admin.initialize_app(cred)
    else:
        # Tenta credenciais default do ambiente (GOOGLE_APPLICATION_CREDENTIALS).
        firebase_admin.initialize_app()
    return firestore.client()


def _fmt_int(n) -> str:
    try:
        return f"{int(n):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


def _fmt_usd(v) -> str:
    try:
        return f"${float(v):,.4f}"
    except (TypeError, ValueError):
        return "$0.0000"


def _sub_table(title: str, entries: dict, total_tokens: int) -> None:
    print(f"\n  {title}")
    if not entries:
        print("    (sem dados)")
        return
    rows = []
    for key, data in entries.items():
        data = data or {}
        rows.append((key, int(data.get("tokens_total") or 0), int(data.get("calls") or 0)))
    rows.sort(key=lambda r: r[1], reverse=True)
    width = max((len(r[0]) for r in rows), default=10)
    for key, toks, calls in rows:
        pct = (toks / total_tokens * 100) if total_tokens else 0
        print(f"    {key:<{width}}  {_fmt_int(toks):>14} tok  {pct:5.1f}%  {_fmt_int(calls):>6} chamadas")


def report_day(db, date_str: str, verbose: bool) -> dict:
    doc = (
        db.collection("system_usage")
        .document("gemini")
        .collection("daily")
        .document(date_str)
        .get()
    )
    if not doc.exists:
        return {}
    data = doc.to_dict() or {}
    tokens = data.get("tokens") or {}
    total = int(tokens.get("total") or 0)
    print(f"\n=== {date_str} ===")
    print(
        f"  Chamadas: {_fmt_int(data.get('calls'))}  |  "
        f"Tokens: {_fmt_int(total)} "
        f"(in={_fmt_int(tokens.get('input'))}, out={_fmt_int(tokens.get('output'))}, "
        f"cache={_fmt_int(tokens.get('cached_input'))})  |  "
        f"Custo estimado: {_fmt_usd(data.get('estimated_usd'))}"
    )
    if verbose:
        _sub_table("Por feature:", data.get("features") or {}, total)
        _sub_table("Por modelo:", data.get("models") or {}, total)
    return data


def _accumulate(agg: dict, data: dict) -> None:
    tokens = data.get("tokens") or {}
    agg["calls"] += int(data.get("calls") or 0)
    agg["estimated_usd"] += float(data.get("estimated_usd") or 0)
    agg["total"] += int(tokens.get("total") or 0)
    for bucket in ("features", "models"):
        for key, d in (data.get(bucket) or {}).items():
            d = d or {}
            slot = agg[bucket].setdefault(key, {"tokens_total": 0, "calls": 0})
            slot["tokens_total"] += int(d.get("tokens_total") or 0)
            slot["calls"] += int(d.get("calls") or 0)


def main():
    parser = argparse.ArgumentParser(description="Readout de uso/custo do Gemini no Hermes.")
    parser.add_argument("--credentials", default=str(DEFAULT_CREDENTIALS))
    parser.add_argument("--days", type=int, default=7, help="Número de dias a partir de hoje (UTC).")
    parser.add_argument("--date", default=None, help="Data específica AAAA-MM-DD (sobrepõe --days).")
    parser.add_argument("--per-day", action="store_true", help="Detalha feature/modelo em cada dia.")
    args = parser.parse_args()

    db = init_firebase(Path(args.credentials))

    if args.date:
        dates = [args.date]
    else:
        today = datetime.now(timezone.utc).date()
        dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(args.days)]
        dates.reverse()

    agg = {"calls": 0, "estimated_usd": 0.0, "total": 0, "features": {}, "models": {}}
    dias_com_dados = 0
    for d in dates:
        data = report_day(db, d, verbose=args.per_day)
        if data:
            dias_com_dados += 1
            _accumulate(agg, data)

    print("\n" + "=" * 60)
    print(f"AGREGADO ({dias_com_dados} dia(s) com dados de {len(dates)} consultado(s))")
    print("=" * 60)
    print(
        f"  Chamadas: {_fmt_int(agg['calls'])}  |  "
        f"Tokens: {_fmt_int(agg['total'])}  |  "
        f"Custo estimado: {_fmt_usd(agg['estimated_usd'])}"
    )
    _sub_table("Onde o gasto se concentra (por feature):", agg["features"], agg["total"])
    _sub_table("Por modelo:", agg["models"], agg["total"])
    print()


if __name__ == "__main__":
    main()
