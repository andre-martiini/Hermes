"""
Resumo semanal do modulo Saude: toda sexta-feira, agrega os ultimos 7 dias de
health_exercise_logs, health_weights, health_waist e health_events num
documento salvo em health_weekly_summaries/{data_fim} e uma mensagem no
Telegram. Sem LLM — e uma agregacao deterministica, nao uma narrativa.
"""

from datetime import datetime, timedelta

from firebase_functions import scheduler_fn, options


def _week_dates(end_date_str: str, days: int = 7) -> list[str]:
    end = datetime.strptime(end_date_str, "%Y-%m-%d")
    return [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def build_weekly_summary(db, week_end: str) -> dict:
    """Monta o resumo da semana que termina em `week_end` (YYYY-MM-DD). Sem efeitos colaterais."""
    week_dates = _week_dates(week_end, 7)
    week_start = week_dates[0]
    prior_week_dates = _week_dates((datetime.strptime(week_start, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d"), 7)

    logs_by_date = {}
    for d in week_dates:
        doc = db.collection("health_exercise_logs").document(d).get()
        if doc.exists:
            logs_by_date[d] = doc.to_dict() or {}

    morning_values, evening_values = [], []
    km_total = 0.0
    strength_sessions = 0
    diet_days = 0
    for log in logs_by_date.values():
        pain = log.get("pain") or {}
        if pain.get("morning") is not None:
            morning_values.append(float(pain["morning"]))
        if pain.get("evening") is not None:
            evening_values.append(float(pain["evening"]))
        for block in (log.get("walkBlocks") or []):
            km_total += float(block.get("distance") or 0)
        if (log.get("strength") or {}).get("done"):
            strength_sessions += 1
        if (log.get("nutrition") or {}).get("plan") == "sim":
            diet_days += 1

    def _weights_in(dates: list[str]) -> list[float]:
        out = []
        for d in dates:
            for doc in db.collection("health_weights").where("date", "==", d).stream():
                w = (doc.to_dict() or {}).get("weight")
                if w is not None:
                    out.append(float(w))
        return out

    avg_weight_week = _avg(_weights_in(week_dates))
    avg_weight_prior = _avg(_weights_in(prior_week_dates))
    weight_delta = (avg_weight_week - avg_weight_prior) if (avg_weight_week is not None and avg_weight_prior is not None) else None

    waist_cm = None
    for d in reversed(week_dates):
        docs = list(db.collection("health_waist").where("date", "==", d).stream())
        if docs:
            waist_cm = (docs[0].to_dict() or {}).get("cm")
            break

    events = []
    for doc in db.collection("health_events").stream():
        data = doc.to_dict() or {}
        if data.get("date") in week_dates:
            events.append({"date": data.get("date"), "label": data.get("label"), "type": data.get("type")})
    events.sort(key=lambda e: e.get("date") or "")

    return {
        "weekStart": week_start,
        "weekEnd": week_end,
        "avgWeight": avg_weight_week,
        "weightDelta": weight_delta,
        "waistCm": waist_cm,
        "avgPainMorning": _avg(morning_values),
        "avgPainEvening": _avg(evening_values),
        "kmTotal": round(km_total, 1),
        "strengthSessions": strength_sessions,
        "strengthGoal": 3,
        "dietDays": diet_days,
        "daysWithLog": len(logs_by_date),
        "events": events,
    }


def format_weekly_summary_message(summary: dict) -> str:
    lines = [f"🗓️ <b>Resumo da semana — {summary['weekStart']} a {summary['weekEnd']}</b>"]

    if summary["avgWeight"] is not None:
        delta = summary["weightDelta"]
        delta_txt = f" ({'+' if delta >= 0 else ''}{delta:.1f} kg vs. semana anterior)" if delta is not None else ""
        lines.append(f"⚖️ Peso médio: <b>{summary['avgWeight']:.1f} kg</b>{delta_txt}")
    else:
        lines.append("⚖️ Peso: sem registros nesta semana.")

    if summary["waistCm"] is not None:
        lines.append(f"📏 Cintura: <b>{summary['waistCm']:.1f} cm</b>")

    if summary["avgPainMorning"] is not None or summary["avgPainEvening"] is not None:
        m = f"{summary['avgPainMorning']:.1f}" if summary["avgPainMorning"] is not None else "-"
        e = f"{summary['avgPainEvening']:.1f}" if summary["avgPainEvening"] is not None else "-"
        lines.append(f"🩻 Dor média — manhã: <b>{m}</b> · noite: <b>{e}</b>")

    lines.append(f"🚶 Caminhada total: <b>{summary['kmTotal']:.1f} km</b>")
    lines.append(f"🏋️ Treino de força: <b>{summary['strengthSessions']}/{summary['strengthGoal']}</b> sessões")
    lines.append(f"🥗 Dias com cardápio seguido: <b>{summary['dietDays']}</b>")

    if summary["events"]:
        lines.append("📌 Eventos da semana:")
        for ev in summary["events"]:
            lines.append(f"  • {ev['date']}: {ev['label']}")

    if summary["daysWithLog"] == 0:
        lines.append("\nNenhum registro diário nesta semana — que tal retomar amanhã?")

    return "\n".join(lines)


@scheduler_fn.on_schedule(
    schedule="0 19 * * 5",
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_512,
    timeout_sec=120,
)
def gerar_resumo_semanal_saude(event: scheduler_fn.ScheduledEvent = None) -> None:
    """Agendada sexta-feira 19h BRT — agrega a semana de saude e envia no Telegram."""
    from main import get_db, _get_telegram_token
    from hermes_core_logic import _get_allowed_chat_id, _send_telegram_message
    from zoneinfo import ZoneInfo

    db = get_db()
    week_end = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")

    summary_ref = db.collection("health_weekly_summaries").document(week_end)
    if summary_ref.get().exists:
        print(f"[ResumoSaude] Resumo da semana terminando em {week_end} já existe.")
        return

    try:
        summary = build_weekly_summary(db, week_end)
        summary_ref.set(summary)
        message = format_weekly_summary_message(summary)
        print(f"[ResumoSaude] {message}")

        chat_id = _get_allowed_chat_id()
        if chat_id:
            _send_telegram_message(_get_telegram_token(db), chat_id, message)
        else:
            print("[ResumoSaude] Nenhum chat_id do Telegram configurado; resumo apenas salvo no Firestore.")
    except Exception as exc:
        print(f"[ResumoSaude] Falha ao gerar resumo semanal: {exc}")
