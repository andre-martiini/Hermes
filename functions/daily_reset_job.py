import datetime
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from firebase_admin import firestore
from firebase_functions import scheduler_fn, options

@scheduler_fn.on_schedule(
    schedule="0 0 * * *", # Every day at midnight
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_256,
    timeout_sec=120,
)
def daily_wip_reset_and_degradation(event: scheduler_fn.ScheduledEvent):
    from main import get_db, _send_telegram_message_raw
    db = get_db()
    sp_tz = zoneinfo.ZoneInfo("America/Sao_Paulo")
    now_sp = datetime.datetime.now(sp_tz)
    today_str = now_sp.strftime("%Y-%m-%d")

    print(f"[Midnight Reset] Running for {today_str}.")

    tasks_ref = db.collection("tarefas")
    active_tasks = tasks_ref.where(
        filter=firestore.FieldFilter("status", "in", ["em andamento", "stand-by"])
    ).get()

    batch = db.batch()
    auto_advanced_count = 0
    sla_breach_count = 0
    degraded_count = 0
    critical_count = 0

    for task_doc in active_tasks:
        task_data = task_doc.to_dict()
        due_date = task_data.get("data_limite", "")
        start_date = task_data.get("data_inicio", "")
        lane = task_data.get("execution_lane", "avanco")

        is_overdue = (due_date and due_date not in ["-", "0000-00-00"] and due_date < today_str) or \
                     (start_date and start_date not in ["-", "0000-00-00"] and start_date < today_str)

        if not is_overdue:
            continue

        updates = {
            "data_limite": today_str,
            "data_inicio": today_str,
            "auto_data_atualizada": True,
            "data_atualizacao": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

        if lane == "aguardando_terceiro":
            title = task_data.get("titulo", "")
            if not title.startswith("[COBRAR]"):
                title = f"[COBRAR] {title}"
            updates["titulo"] = title
            updates["execution_lane"] = "avanco"
            sla_breach_count += 1
        else:
            if task_data.get("status") == "em andamento":
                degraded_count += 1
                curr_deg = task_data.get("degradation_count", 0) + 1
                updates["degradation_count"] = curr_deg
                if curr_deg >= 3:
                    critical_count += 1
            auto_advanced_count += 1

        batch.update(task_doc.reference, updates)

    if auto_advanced_count > 0 or sla_breach_count > 0:
        batch.commit()
        print(f"[Midnight Reset] Committed. Advanced: {auto_advanced_count}, SLA Breaches: {sla_breach_count}.")

        summary = f"🕛 <b>Virada do Dia ({today_str}):</b>\n\n"
        if auto_advanced_count > 0:
            summary += f"🔄 {auto_advanced_count} ação(ões) atrasada(s) foram automaticamente atualizadas para a data de hoje.\n"
            if critical_count > 0:
                summary += f"⚠️ <b>{critical_count} atingiram nível vermelho crítico (3+ adiamentos)!</b> Expurgo necessário.\n"

        if sla_breach_count > 0:
            summary += f"📞 {sla_breach_count} ação(ões) estouraram o SLA de espera e viraram [COBRAR].\n"

        summary += "\nAbra o painel e puxe suas tarefas de foco do dia."

        settings_doc = db.collection("system").document("settings").get()
        chat_id = settings_doc.to_dict().get("telegram_admin_chat_id") if settings_doc.exists else None

        if chat_id:
            try:
                _send_telegram_message_raw(db, chat_id, summary)
            except Exception as e:
                print(f"[Midnight Reset] Failed to send telegram: {e}")
    else:
        print("[Midnight Reset] No overdue tasks to reset.")