"""
Relatorio Semanal do Hermes (N14) -- Fase 1: placa de resultado 100% em codigo,
sem regras de decisao (adjustment) e sem modelo escrevendo texto. As fases 2 e
3 (regras de decisao / narrativa do modelo) sao propositalmente separadas
desta, para que o alicerce fique de pe sozinho se as proximas atrasarem.

Roda todo domingo as 19h BRT. Semana = segunda 00:00 a domingo 18:59 BRT.
Persiste em health_weekly_reports/{YYYY-Www}.
"""
from datetime import datetime, timedelta, timezone

from firebase_functions import scheduler_fn, options

_RADICULAR_ORDER = ["gluteo", "quadril", "coxa", "joelho", "panturrilha", "tornozelo", "pe"]


def _week_bounds(reference_date: str):
    """reference_date (YYYY-MM-DD) deve ser um domingo. Retorna (week_start, week_end)."""
    ref = datetime.strptime(reference_date, "%Y-%m-%d")
    week_start = ref - timedelta(days=6)
    return week_start.strftime("%Y-%m-%d"), reference_date


def _dates_in_range(start: str, end: str) -> list[str]:
    d0 = datetime.strptime(start, "%Y-%m-%d")
    d1 = datetime.strptime(end, "%Y-%m-%d")
    return [(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((d1 - d0).days + 1)]


def iso_week_key(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _avg(values):
    return sum(values) / len(values) if values else None


def _weight_avg7(db, as_of_date: str):
    """Media dos registros de peso nos 7 dias terminando em as_of_date (inclusive).
    None se houver menos de 3 registros -- media de 2 pontos nao e confiavel."""
    start = (datetime.strptime(as_of_date, "%Y-%m-%d") - timedelta(days=6)).strftime("%Y-%m-%d")
    docs = (
        db.collection("health_weights")
        .where("date", ">=", start)
        .where("date", "<=", as_of_date)
        .stream()
    )
    values = [d.to_dict().get("weight") for d in docs if d.to_dict().get("weight") is not None]
    return _avg(values) if len(values) >= 3 else None


def _waist_for_week(db, week_start: str, week_end: str):
    docs = list(
        db.collection("health_waist")
        .where("date", ">=", week_start)
        .where("date", "<=", week_end)
        .stream()
    )
    if not docs:
        return {"value": None, "delta": None}
    latest = max(docs, key=lambda d: d.to_dict().get("date", ""))
    value = latest.to_dict().get("cm")

    prev_start = (datetime.strptime(week_start, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    prev_end = (datetime.strptime(week_end, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    prev_docs = list(
        db.collection("health_waist")
        .where("date", ">=", prev_start)
        .where("date", "<=", prev_end)
        .stream()
    )
    delta = None
    if prev_docs and value is not None:
        prev_value = max(prev_docs, key=lambda d: d.to_dict().get("date", "")).to_dict().get("cm")
        if prev_value is not None:
            delta = round(value - prev_value, 2)
    return {"value": value, "delta": delta}


def _logs_for_week(db, week_start: str, week_end: str) -> dict:
    logs = {}
    for d in _dates_in_range(week_start, week_end):
        doc = db.collection("health_exercise_logs").document(d).get()
        if doc.exists:
            logs[d] = doc.to_dict() or {}
    return logs


def _most_distal_location(logs: dict):
    """Maior indice em _RADICULAR_ORDER entre os registros da semana com sintoma
    presente (exclui 'nenhum'/ausente). None se nao houver nenhum registro."""
    best_idx = None
    for data in logs.values():
        loc = (data.get("radicular") or {}).get("location")
        if loc in _RADICULAR_ORDER:
            idx = _RADICULAR_ORDER.index(loc)
            if best_idx is None or idx > best_idx:
                best_idx = idx
    return best_idx


def _radicular_trend(this_week_idx, last_week_idx) -> str:
    if this_week_idx is None or last_week_idx is None:
        return "sem_dado"
    if this_week_idx > last_week_idx:
        return "descendo"  # mais distal = pior (McKenzie: periferalizacao)
    if this_week_idx < last_week_idx:
        return "subindo"  # mais proximal = melhor (centralizacao)
    return "estável"


def build_weekly_report_card(db, week_end: str) -> dict:
    """Monta a placa de resultado da semana terminando em week_end (domingo,
    YYYY-MM-DD). Somente leitura -- sem efeitos colaterais."""
    week_start, week_end = _week_bounds(week_end)
    prev_week_end = (datetime.strptime(week_start, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_week_start, _ = _week_bounds(prev_week_end)

    logs = _logs_for_week(db, week_start, week_end)
    prev_logs = _logs_for_week(db, prev_week_start, prev_week_end)

    weight_avg7 = _weight_avg7(db, week_end)
    weight_avg7_prev = _weight_avg7(db, prev_week_end)
    weight_delta = (
        round(weight_avg7 - weight_avg7_prev, 2)
        if weight_avg7 is not None and weight_avg7_prev is not None
        else None
    )

    km_total = 0.0
    km_days = 0
    for data in logs.values():
        day_km = sum((b.get("distance") or 0) for b in (data.get("walkBlocks") or []))
        if day_km > 0:
            km_total += day_km
            km_days += 1

    morning_vals = [data["pain"]["morning"] for data in logs.values() if (data.get("pain") or {}).get("morning") is not None]
    evening_vals = [data["pain"]["evening"] for data in logs.values() if (data.get("pain") or {}).get("evening") is not None]

    this_week_idx = _most_distal_location(logs)
    last_week_idx = _most_distal_location(prev_logs)

    therapy_planned_docs = (
        db.collection("health_events")
        .where("source", "==", "calendar")
        .where("date", ">=", week_start)
        .where("date", "<=", week_end)
        .stream()
    )
    therapy_planned = sum(
        1 for d in therapy_planned_docs if d.to_dict().get("type") in ("fisioterapia", "modalidade_terapeutica")
    )

    checkin_days = sum(
        1 for data in logs.values()
        if (data.get("pain") or {}).get("morning") is not None
        and (data.get("pain") or {}).get("evening") is not None
    )

    sleep_vals = [data["sleepQuality"]["quality"] for data in logs.values() if (data.get("sleepQuality") or {}).get("quality") is not None]

    return {
        "week_start": week_start,
        "week_end": week_end,
        "weight_avg7": weight_avg7,
        "weight_delta": weight_delta,
        "waist": _waist_for_week(db, week_start, week_end),
        "km_total": round(km_total, 2),
        "km_days": km_days,
        "pain_morning_avg": round(_avg(morning_vals), 1) if len(morning_vals) >= 4 else None,
        "pain_evening_avg": round(_avg(evening_vals), 1) if len(evening_vals) >= 4 else None,
        "radicular_trend": _radicular_trend(this_week_idx, last_week_idx),
        "strength_done": sum(1 for data in logs.values() if (data.get("strength") or {}).get("done")),
        "strength_planned": 3,
        "therapy_done": sum(1 for data in logs.values() if data.get("therapy")),
        "therapy_planned": therapy_planned,
        "checkin_adherence": round(checkin_days / 7, 2),
        "sleep_avg": round(_avg(sleep_vals), 1) if len(sleep_vals) >= 4 else None,
    }


@scheduler_fn.on_schedule(
    schedule="0 19 * * 0",
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_512,
    timeout_sec=120,
)
def gerar_relatorio_semanal_saude(event: scheduler_fn.ScheduledEvent = None) -> None:
    """Agendada domingo 19h BRT -- monta a placa de resultado (Fase 1) e persiste
    em health_weekly_reports. Sem regras de decisao nem modelo (fases 2 e 3)."""
    from main import get_db, _get_telegram_token
    from hermes_core_logic import _get_allowed_chat_id, _send_telegram_message
    from zoneinfo import ZoneInfo

    db = get_db()
    week_end = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")
    report_id = iso_week_key(week_end)

    report_ref = db.collection("health_weekly_reports").document(report_id)
    if report_ref.get().exists:
        print(f"[RelatorioSaude] Relatório {report_id} já existe.")
        return

    try:
        card = build_weekly_report_card(db, week_end)
        report_ref.set({
            "card": card,
            "adjustment": None,
            "text": None,
            "audit": None,
            "prompt_version": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"[RelatorioSaude] {report_id}: {card}")

        chat_id = _get_allowed_chat_id()
        if not chat_id:
            print("[RelatorioSaude] Nenhum chat_id configurado; relatório apenas salvo no Firestore.")
            return

        parts = []
        if card["weight_avg7"] is not None:
            parts.append(f"peso média 7d {card['weight_avg7']:.1f} kg")
        parts.append(f"{card['km_total']:.1f} km em {card['km_days']} dia(s)")
        parts.append(f"força {card['strength_done']}/{card['strength_planned']}")
        resumo = ", ".join(parts) + "."
        message = f"📊 Relatório semanal disponível ({card['week_start']} a {card['week_end']}).\n\n{resumo}"
        _send_telegram_message(_get_telegram_token(db), chat_id, message)
    except Exception as exc:
        print(f"[RelatorioSaude] Falha ao gerar relatório semanal: {exc}")
